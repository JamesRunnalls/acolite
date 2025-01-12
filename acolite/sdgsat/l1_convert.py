## def l1_convert
## converts SDGSAT-1 KX10 MII bundle to l1r NetCDF for acolite-gen
## written by Quinten Vanhellemont, RBINS
## 2023-01-03
## modifications:

def l1_convert(inputfile, output = None, settings = {}, verbosity=5):
    import os
    import dateutil.parser, time
    import numpy as np
    import acolite as ac

    #import os, zipfile, shutil
    #import re

    if 'verbosity' in settings: verbosity = settings['verbosity']

    ## parse inputfile
    if type(inputfile) != list:
        if type(inputfile) == str:
            inputfile = inputfile.split(',')
        else:
            inputfile = list(inputfile)
    nscenes = len(inputfile)
    if verbosity > 1: print('Starting conversion of {} scenes'.format(nscenes))

    new = True
    warp_to = None

    ofile = None
    ofiles = []
    setu = {}

    for bundle in inputfile:
        t0 = time.time()
        ## find meta and cal for given bundle
        metafiles, calfiles, imgfiles = ac.sdgsat.bundle_test(bundle)

        ## run through metafiles
        for mi, mf in enumerate(metafiles):
            cf = calfiles[mi]
            im = imgfiles[mi]

            ## read meta and calibration
            meta = ac.sdgsat.metadata(mf)
            cal = ac.sdgsat.calibration(cf)

            ## identify sensor
            sensor = '{}_{}'.format(meta['SatelliteID'], meta['SensorID'])
            ## read rsr
            rsrd = ac.shared.rsr_dict(sensor)[sensor]

            ## parse sensor settings
            setu = ac.acolite.settings.parse(sensor, settings=settings)
            if output is None:
                if setu['output'] is None:
                    output = os.path.dirname(mf)
                else:
                    output = setu['output']

            gains = None
            if setu['gains']:
                if (len(setu['gains_toa']) == len(rsrd['rsr_bands'])) &\
                   (len(setu['offsets_toa']) == len(rsrd['rsr_bands'])):
                   gains = {}
                   for bi, band in enumerate(rsrd['rsr_bands']):
                       gains[band] = {'gain': float(setu['gains_toa'][bi]),
                                    'offset': float(setu['offsets_toa'][bi])}
                else:
                    print('Use of gains requested, but provided number of gain ({}) or offset ({}) values does not match number of bands in RSR ({})'.format(len(setu['gains_toa']), len(setu['offsets_toa']), len(rsr_bands)))
                    print('Provide gains in band order: {}'.format(','.join(rsrd['rsr_bands'])))

            verbosity = setu['verbosity']

            clip, clip_mask = False, None
            limit = setu['limit']
            poly = setu['polygon']
            if poly is not None:
                if os.path.exists(poly):
                    try:
                        limit = ac.shared.polygon_limit(poly)
                        if setu['polygon_limit']:
                            print('Using limit from polygon envelope: {}'.format(limit))
                        else:
                            limit = setu['limit']
                        clip = True
                    except:
                        print('Failed to import polygon {}'.format(poly))

            ## geometry
            saa = float(meta['SolarAzimuth'])
            sza = float(meta['SolarZenith'])
            vza = 5.0 ## suggested by lwk1542
            vaa = 0.0 ## azi not so important for low vza
            raa = np.abs(saa-vaa)
            while raa > 180: raa = abs(raa-360)

            dtime = dateutil.parser.parse(meta['CenterTime-Acamera'])
            isodate = dtime.isoformat()
            doy = dtime.strftime('%j')
            se_distance = ac.shared.distance_se(doy)

            ## get F0 for radiance -> reflectance computation
            f0 = ac.shared.f0_get(f0_dataset=setu['solar_irradiance_reference'])
            f0_b = ac.shared.rsr_convolute_dict(f0['wave']/1000, f0['data']*10, rsrd['rsr'])

            ## make global attributes for L1R NetCDF
            gatts = {'sensor':sensor, 'isodate':isodate, #'global_dims':global_dims,
                     'sza':sza, 'vza':vza, 'raa':raa, 'vaa': vaa, 'saa': saa,
                     'doy': doy, 'se_distance': se_distance,
                     'mus': np.cos(sza*(np.pi/180.)), 'acolite_file_type': 'L1R'}

            ## add band info to gatts
            for b in rsrd['rsr_bands']:
                gatts['{}_wave'.format(b)] = rsrd['wave_nm'][b]
                gatts['{}_name'.format(b)] = rsrd['wave_name'][b]
                gatts['{}_f0'.format(b)] = f0_b[b]

            oname = '{}_{}'.format(gatts['sensor'], dtime.strftime('%Y_%m_%d_%H_%M_%S'))
            if setu['region_name'] != '': oname+='_{}'.format(setu['region_name'])
            ofile = '{}/{}_L1R.nc'.format(output, oname)
            gatts['oname'] = oname
            gatts['ofile'] = ofile

            ## read image projection
            dct = ac.shared.projection_read(im)

            sub = None
            warp_to = None

            ## check crop
            if (sub is None) & (limit is not None):
                dct_sub = ac.shared.projection_sub(dct, limit, four_corners=True)
                if dct_sub['out_lon']:
                    if verbosity > 1: print('Longitude limits outside {}'.format(bundle))
                    continue
                if dct_sub['out_lat']:
                    if verbosity > 1: print('Latitude limits outside {}'.format(bundle))
                    continue
                sub = dct_sub['sub']

            if sub is None:
                dct_prj = {k:dct[k] for k in dct}
            else:
                gatts['sub'] = sub
                gatts['limit'] = limit
                ## get the target NetCDF dimensions and dataset offset
                if (warp_to is None):
                    if (setu['extend_region']): ## include part of the roi not covered by the scene
                        dct_prj = {k:dct_sub['region'][k] for k in dct_sub['region']}
                    else: ## just include roi that is covered by the scene
                        dct_prj = {k:dct_sub[k] for k in dct_sub}
                ## end cropped

            gatts['scene_xrange'] = dct_prj['xrange']
            gatts['scene_yrange'] = dct_prj['yrange']
            gatts['scene_proj4_string'] = dct_prj['proj4_string']
            gatts['scene_pixel_size'] = dct_prj['pixel_size']
            gatts['scene_dims'] = dct_prj['dimensions']
            if 'zone' in dct_prj: gatts['scene_zone'] = dct_prj['zone']

            ## get projection info for netcdf
            if setu['netcdf_projection']:
                nc_projection = ac.shared.projection_netcdf(dct_prj, add_half_pixel=True)
            else:
                nc_projection = None

            ## save projection keys in gatts
            pkeys = ['xrange', 'yrange', 'proj4_string', 'pixel_size', 'zone']
            for k in pkeys:
                if k in dct_prj: gatts[k] = dct_prj[k]

            ## warp settings for read_band
            xyr = [min(dct_prj['xrange']),
                    min(dct_prj['yrange']),
                    max(dct_prj['xrange']),
                    max(dct_prj['yrange']),
                    dct_prj['proj4_string']]

            res_method = 'average'
            warp_to = (dct_prj['proj4_string'], xyr, dct_prj['pixel_size'][0],dct_prj['pixel_size'][1], res_method)

            ## store scene and output dimensions
            gatts['scene_dims'] = dct['ydim'], dct['xdim']
            gatts['global_dims'] = dct_prj['dimensions']

            ## new file for every bundle if not merging
            new = True

            ## if we are clipping to a given polygon get the clip_mask here
            if clip:
                clip_mask = ac.shared.polygon_crop(dct_prj, poly, return_sub=False)
                clip_mask = clip_mask.astype(bool) == False

            ## write lat/lon
            if (setu['output_geolocation']):
                if verbosity > 1: print('Writing geolocation lon/lat')
                lon, lat = ac.shared.projection_geo(dct_prj, add_half_pixel=True)
                ac.output.nc_write(ofile, 'lon', lon, attributes=gatts, new=new, double=True, nc_projection=nc_projection,
                                        netcdf_compression=setu['netcdf_compression'],
                                        netcdf_compression_level=setu['netcdf_compression_level'])
                if verbosity > 1: print('Wrote lon ({})'.format(lon.shape))
                lon = None

                ac.output.nc_write(ofile, 'lat', lat, double=True,
                                        netcdf_compression=setu['netcdf_compression'],
                                        netcdf_compression_level=setu['netcdf_compression_level'])
                if verbosity > 1: print('Wrote lat ({})'.format(lat.shape))
                lat = None
                new=False

            ## write x/y
            if (setu['output_xy']):
                if verbosity > 1: print('Writing geolocation x/y')
                x, y = ac.shared.projection_geo(dct_prj, xy=True, add_half_pixel=True)
                ac.output.nc_write(ofile, 'xm', x, new=new,
                                    netcdf_compression=setu['netcdf_compression'],
                                    netcdf_compression_level=setu['netcdf_compression_level'])
                if verbosity > 1: print('Wrote xm ({})'.format(x.shape))
                x = None
                ac.output.nc_write(ofile, 'ym', y,
                                    netcdf_compression=setu['netcdf_compression'],
                                    netcdf_compression_level=setu['netcdf_compression_level'])
                if verbosity > 1: print('Wrote ym ({})'.format(y.shape))
                y = None
                new=False

            ## read bands
            for i, b in enumerate(cal):
                bi = int(b)
                band = rsrd['rsr_bands'][i]

                ## read data and convert to Lt
                md, data = ac.shared.read_band(im, idx=bi, warp_to=warp_to, gdal_meta=True)
                nodata = data == np.uint16(0)
                data = data.astype(float) * cal[b]['gain'] + cal[b]['bias']

                ## apply gains
                if (gains != None) & (setu['gains_parameter'] == 'radiance'):
                    print('Applying gain {} and offset {} to TOA radiance for band {}'.format(gains[band]['gain'], gains[band]['offset'], band))
                    data = gains[band]['gain'] * data + gains[band]['offset']

                ds_att = {'wavelength':rsrd['wave_nm'][band]}
                if gains != None:
                    ds_att['gain'] = gains[band]['gain']
                    ds_att['offset'] = gains[band]['offset']
                    ds_att['gains_parameter'] = setu['gains_parameter']

                if setu['output_lt']:
                    ds = 'Lt_{}'.format(rsrd['wave_name'][band])
                    ## write toa radiance
                    ac.output.nc_write(ofile, ds, data,
                                  dataset_attributes = ds_att,
                                  netcdf_compression=setu['netcdf_compression'],
                                  netcdf_compression_level=setu['netcdf_compression_level'],
                                  netcdf_compression_least_significant_digit=setu['netcdf_compression_least_significant_digit'])

                ## convert to rhot
                ds = 'rhot_{}'.format(rsrd['wave_name'][band])
                f0 = gatts['{}_f0'.format(band)]/10
                data *= (np.pi * gatts['se_distance']**2) / (f0 * np.nanmean(gatts['mus']))

                ## apply gains
                if (gains != None) & (setu['gains_parameter'] == 'reflectance'):
                    print('Applying gain {} and offset {} to TOA reflectance for band {}'.format(gains[band]['gain'], gains[band]['offset'], band))
                    data = gains[band]['gain'] * data + gains[band]['offset']

                data[nodata] = np.nan
                if clip: data[clip_mask] = np.nan

                ## write to netcdf file
                ac.output.nc_write(ofile, ds, data, replace_nan=True, attributes=gatts,
                                        new=new, dataset_attributes = ds_att, nc_projection=nc_projection,
                                        netcdf_compression=setu['netcdf_compression'],
                                        netcdf_compression_level=setu['netcdf_compression_level'],
                                        netcdf_compression_least_significant_digit=setu['netcdf_compression_least_significant_digit'])
                new = False
                if verbosity > 1: print('Converting bands: Wrote {} ({})'.format(ds, data.shape))


        if verbosity > 1:
            print('Conversion took {:.1f} seconds'.format(time.time()-t0))
            print('Created {}'.format(ofile))

        if limit is not None: sub = None
        if ofile not in ofiles: ofiles.append(ofile)

    return(ofiles, setu)
