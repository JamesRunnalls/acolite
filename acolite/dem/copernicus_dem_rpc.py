## def copernicus_dem_rpc
## combines copernicus dem files for a given region
## code from ac.shared.warp_and_merge
## written by Quinten Vanhellemont, RBINS
## 2022-09-22
## modifications:

def copernicus_dem_rpc(dct_limit, output=None):
    import acolite as ac
    import os
    from osgeo import gdal, gdalconst
    if gdal.__version__ < '3.3':
        from osgeo.utils import gdal_merge
    else:
        from osgeo_utils import gdal_merge

    if output == None: output = '{}'.format(ac.config['scratch_dir'])
    pos = dct_limit['p']((dct_limit['xrange'][0],dct_limit['xrange'][0],\
                          dct_limit['xrange'][1],dct_limit['xrange'][1]),\
                         (dct_limit['yrange'][0],dct_limit['yrange'][1],\
                          dct_limit['yrange'][0],dct_limit['yrange'][1]), inverse=True)
    pos_limit = [min(pos[1]), min(pos[0]), max(pos[1]), max(pos[0])]
    dem_files = ac.dem.copernicus_dem_find(pos_limit)

    if len(dem_files) == 1:
        rpc_dem = dem_files[0]
    elif len(dem_files) > 1:
        rpc_dem ='{}/dem_merged.tif'.format(output)
        if os.path.exists(rpc_dem): os.remove(rpc_dem)
        print('Merging {} tiles to {}'.format(len(dem_files), rpc_dem))
        gdal_merge.main(['', '-o', rpc_dem, '-n', '0']+dem_files)
    return(rpc_dem)
