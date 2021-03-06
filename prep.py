"""
Prepare a dataset (specifically an orthorectified Sentinel 1 scene in BEAM-DIMAP format) for datacube indexing.

Note, this script is only an example. For production purposes, more metadata would be harvested.

The BEAM-DIMAP format (output by Sentinel Toolbox/SNAP) consists of an XML header file (.dim)
and a directory (.data) which stores different polarisations (different raster bands) separately,
each as ENVI format, that is, raw binary (.img) with ascii header (.hdr). GDAL can read ENVI
format (that is, when provided an img it checks for an accompanying hdr).
"""

# get corner coords in crs of source datafile,
# transform into crs of datacube index.
#
# TODO: datacube could perform this transformation itself rather than entrusting yamls.
# This may support more careful consideration of datums, and issues such as the corner 
# coords failing to enclose the area due to curvature of the projected border segments.
import rasterio.warp
from osgeo import osr
def get_geometry(path):
    with rasterio.open(path) as img:
        left, bottom, right, top = img.bounds
        crs = str(str(getattr(img, 'crs_wkt', None) or img.crs.wkt))
        corners = {
                    'ul': {'x': left, 'y': top},
                    'ur': {'x': right, 'y': top},
                    'll': {'x': left, 'y': bottom},
                    'lr': {'x': right, 'y': bottom} 
                  }
        projection = {'spatial_reference': crs, 'geo_ref_points': corners}

        spatial_ref = osr.SpatialReference(crs)
        t = osr.CoordinateTransformation(spatial_ref, spatial_ref.CloneGeogCS())
        def transform(p):
            lon, lat, z = t.TransformPoint(p['x'], p['y'])
            return {'lon': lon, 'lat': lat}
        extent = {key: transform(p) for key,p in corners.items()}

        return projection, extent


# Construct metadata dict
import uuid
from xml.etree import ElementTree # should use cElementTree..
from dateutil import parser
import os
def prep_dataset(path):
    # input: path = .dim filename

    # Read in the XML header

    xml = ElementTree.parse(str(path)).getroot().find(
        "Dataset_Sources/MDElem[@name='metadata']/MDElem[@name='Abstracted_Metadata']")
    scene_name = xml.find("MDATTR[@name='PRODUCT']").text
    platform = xml.find("MDATTR[@name='MISSION']").text.replace('-','_')
    t0 = parser.parse(xml.find("MDATTR[@name='first_line_time']").text)
    t1 = parser.parse(xml.find("MDATTR[@name='last_line_time']").text)

    # TODO: which time goes where in what format?
    # could also read processing graph, or
    # could read production/productscenerasterstart(stop)time

    # get bands

    # TODO: verify band info from xml
    
    bands = ['vh','vv']
    bandpaths = [str(os.path.join(path[:-3]+'data','Gamma0_' + pol.upper() + '.img'))
    			for pol in bands]
       
    # trusting bands coaligned, use one to generate spatial bounds for all

    projection, extent = get_geometry(bandpaths[0])
    
    # format metadata (i.e. construct hashtable tree for syntax of file interface)

    return {
        'id': str(uuid.uuid4()),
        'processing_level': "terrain",
        'product_type': "gamma0",
        #'creation_dt':  t0,
        'platform': {'code': 'SENTINEL_1'},
        'instrument': {'name': 'SAR'},
        'extent': { 'coord': extent, 'from_dt': str(t0), 'to_dt': str(t1), 'center_dt': str(t0+(t1-t0)/2) },
        'format': {'name': 'ENVI'}, # ENVI or BEAM-DIMAP ?
        'grid_spatial': {'projection': projection},
        'image': { 'bands': {b: {'path': p, 'nodata': 0} for b,p in zip(bands,bandpaths)} },
        'lineage': {'source_datasets': {}, 'ga_label': scene_name} # TODO!
        # C band, etc...
    }



import sys
import yaml

if len(sys.argv) != 2:
    print("Usage: python prep.py scene.dim")
    print("or (bulk usage): for file in *.dim; do python prep.py $file; done")
else:
    scene = sys.argv[-1]
    assert scene.lower().endswith('.dim'), "Expect the BEAM-DIMAP header file as input"
    metadata = prep_dataset(scene)
    yaml_path = scene[:-3] + 'yaml' # change suffix

    with open(yaml_path,'w') as stream:
        yaml.dump(metadata,stream)
