#!/usr/bin/env python
"""Download tiles from Google Drive to local folder."""

import subprocess
import os

def main():
    gdrive_folder = 'Africa_CPI_Sentinel2'
    local_folder = os.path.expanduser('~/Downloads/Africa_CPI_Sentinel2')
    
    cmd = [
        'rclone', 'sync',
        f'gdrive:{gdrive_folder}',
        local_folder,
        '--progress'
    ]
    
    print(f"Downloading gdrive:{gdrive_folder} → {local_folder}")
    subprocess.run(cmd)
    print(f"\n✓ Done! Files in: {local_folder}")

if __name__ == '__main__':
    main()