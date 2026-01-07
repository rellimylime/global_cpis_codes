"""
Create an interactive map showing which tiles exist and their IDs.
"""

import folium
import geopandas as gpd
from shapely.geometry import box
import json
import os
import subprocess
import re

def generate_all_tiles():
    """
    Generate tile metadata from grid parameters (no GEE involved).
    This is just math - recreates the same grid used in download_africa_gee.py
    """
    AFRICA_BBOX = [-17.6, -35.0, 51.4, 37.3]
    GRID_SIZE = 2.0
    
    tiles = {}
    tile_id = 0
    lon = AFRICA_BBOX[0]
    
    while lon < AFRICA_BBOX[2]:
        lat = AFRICA_BBOX[1]
        while lat < AFRICA_BBOX[3]:
            bbox = [lon, lat, 
                   min(lon + GRID_SIZE, AFRICA_BBOX[2]), 
                   min(lat + GRID_SIZE, AFRICA_BBOX[3])]
            tiles[tile_id] = {
                'bbox': bbox,
                'center': [(bbox[1] + bbox[3])/2, (bbox[0] + bbox[2])/2]
            }
            tile_id += 1
            lat += GRID_SIZE
        lon += GRID_SIZE
    
    return tiles

def get_gdrive_tile_ids():
    """Get list of tile IDs that exist in Google Drive."""
    result = subprocess.run(
        ['rclone', 'lsf', 'gdrive:Africa_CPI_Sentinel2'],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        return set()
    
    tile_ids = set()
    for line in result.stdout.split('\n'):
        match = re.search(r'tile_(\d+)', line)
        if match:
            tile_ids.add(int(match.group(1)))
    
    return tile_ids

def get_arid_tile_ids():
    """Get cached arid tile IDs."""
    cache_file = 'arid_tile_ids.json'
    if os.path.exists(cache_file):
        with open(cache_file, 'r') as f:
            return set(json.load(f))
    return set()

def create_map():
    """Create interactive map."""
    
    print("Loading data...")
    
    # Generate ALL tiles (just math, no downloads)
    tiles = generate_all_tiles()
    
    # Get which tiles exist in Google Drive
    gdrive_tiles = get_gdrive_tile_ids()
    
    # Get arid tiles
    arid_tiles = get_arid_tile_ids()
    
    # Load arid regions shapefile
    arid_gdf = None
    if os.path.exists('Africa_Arid_Regions_All-shp'):
        arid_gdf = gpd.read_file('Africa_Arid_Regions_All-shp')
        if arid_gdf.crs != 'EPSG:4326':
            arid_gdf = arid_gdf.to_crs('EPSG:4326')
    
    print(f"Total tiles in grid: {len(tiles)}")
    print(f"Tiles in Google Drive: {len(gdrive_tiles)}")
    print(f"Arid tiles: {len(arid_tiles)}")
    
    # Create map centered on Africa
    m = folium.Map(location=[5, 20], zoom_start=4)
    
    # Add arid regions layer
    if arid_gdf is not None:
        folium.GeoJson(
            arid_gdf,
            name='Arid Regions',
            style_function=lambda x: {
                'fillColor': '#ffff00',
                'color': '#ffff00',
                'weight': 1,
                'fillOpacity': 0.2
            }
        ).add_to(m)
    
    # Add tiles
    for tile_id, tile_data in tiles.items():
        bbox = tile_data['bbox']
        center = tile_data['center']
        
        # Determine tile status
        in_gdrive = tile_id in gdrive_tiles
        in_arid = tile_id in arid_tiles
        
        # Color coding
        if in_gdrive and in_arid:
            color = '#00ff00'  # Green - exists and in arid region
            status = 'In GDrive (arid)'
        elif in_gdrive and not in_arid:
            color = '#ff0000'  # Red - exists but NOT in arid region
            status = 'In GDrive (not arid - DELETE)'
        elif not in_gdrive and in_arid:
            color = '#0000ff'  # Blue - not downloaded but in arid region
            status = 'Not in GDrive (arid - should download)'
        else:
            color = '#cccccc'  # Gray - not downloaded, not arid
            status = 'Not in GDrive (not arid)'
        
        # Create rectangle for tile
        bounds = [[bbox[1], bbox[0]], [bbox[3], bbox[2]]]
        
        popup_html = f"""
        <b>Tile ID: {tile_id}</b><br>
        Status: {status}<br>
        Bounds: {bbox[1]:.2f}°S to {bbox[3]:.2f}°N<br>
        &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{bbox[0]:.2f}°W to {bbox[2]:.2f}°E
        """
        
        folium.Rectangle(
            bounds=bounds,
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"Tile {tile_id}",
            color=color,
            fill=True,
            fillOpacity=0.3,
            weight=1
        ).add_to(m)
        
        # Add tile ID label at center
        folium.Marker(
            location=center,
            icon=folium.DivIcon(html=f"""
                <div style="font-size: 8pt; color: black; font-weight: bold; 
                            text-shadow: 1px 1px 1px white, -1px -1px 1px white, 
                                         1px -1px 1px white, -1px 1px 1px white;">
                    {tile_id}
                </div>
            """)
        ).add_to(m)
    
    # Add legend
    legend_html = '''
    <div style="position: fixed; 
                bottom: 50px; right: 50px; width: 250px; height: 180px; 
                background-color: white; border:2px solid grey; z-index:9999; 
                font-size:14px; padding: 10px">
    <p><b>Tile Status:</b></p>
    <p><span style="color: #00ff00;">█</span> In GDrive (arid region)</p>
    <p><span style="color: #ff0000;">█</span> In GDrive (NOT arid - DELETE)</p>
    <p><span style="color: #0000ff;">█</span> Not in GDrive (arid - need)</p>
    <p><span style="color: #cccccc;">█</span> Not in GDrive (not arid)</p>
    <p><span style="background-color: #ffff00; padding: 2px;">█</span> Arid regions shapefile</p>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(legend_html))
    
    # Add layer control
    folium.LayerControl().add_to(m)
    
    # Save map
    output_file = 'africa_tiles_map.html'
    m.save(output_file)
    
    print(f"\n✓ Map saved to: {output_file}")
    print(f"  Open it in a browser to see tile IDs and status")
    
    return output_file

if __name__ == '__main__':
    print("="*80)
    print("Creating Africa Tiles Visualization Map")
    print("="*80)
    
    create_map()