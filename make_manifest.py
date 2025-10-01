#!/usr/bin/env python3
import xml.etree.ElementTree as ET
import json
import sys
from pathlib import Path

def make_manifest(dzi_path: Path):
    try:
        dzi_path = Path(dzi_path)
        if not dzi_path.exists(): return
        tree = ET.parse(str(dzi_path))
        root = tree.getroot()
        ns = "http://schemas.microsoft.com/deepzoom/2008"
        size = root.find(f"{{{ns}}}Size")
        if size is None: return

        width = int(size.attrib['Width'])
        height = int(size.attrib['Height'])
        tile_size = int(root.attrib.get("TileSize", 512))

        manifest = {
            "width": width,
            "height": height,
            "tileSize": tile_size,
            "dzi": dzi_path.name
        }
        out = dzi_path.parent / "manifest.json"
        out.write_text(json.dumps(manifest, indent=2))
    except Exception:
        pass

if __name__ == "__main__":
    if len(sys.argv) > 1:
        make_manifest(Path(sys.argv[1]))