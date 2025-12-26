import rioxarray as rioxr
import matplotlib.pyplot as plt

tif1 = rioxr.open_rasterio("imgs/africa_s2_2021_tile_0144-0000000000-0000000000.tif")
tif2 = rioxr.open_rasterio("imgs/africa_s2_2021_tile_0144-0000000000-0000011776.tif")
tif3 = rioxr.open_rasterio("imgs/africa_s2_2021_tile_0144-0000011776-0000011776.tif")
tif4 = rioxr.open_rasterio("imgs/africa_s2_2021_tile_0144-0000011776-0000000000.tif")

tif1.sel(band=[1, 2, 3]).plot.imshow(rgb='band', robust=True)
plt.savefig("tif1.png")

tif2.sel(band=[1, 2, 3]).plot.imshow(rgb='band', robust=True)
plt.savefig("tif2.png")

tif3.sel(band=[1, 2, 3]).plot.imshow(rgb='band', robust=True)
plt.savefig("tif3.png")

tif4.sel(band=[1, 2, 3]).plot.imshow(rgb='band', robust=True)
plt.savefig("tif4.png")