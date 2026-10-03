"""Fetch app-local Microsoft runtime from conda-forge; never install system-wide."""
import hashlib
import io
import json
import struct
from pathlib import Path
import tarfile
import urllib.request
import zipfile
from compression import zstd

root = Path(__file__).resolve().parents[1]
target = root / "tools" / "runtime"
target.mkdir(parents=True, exist_ok=True)
url = "https://conda.anaconda.org/conda-forge/win-64/current_repodata.json"
with urllib.request.urlopen(url, timeout=60) as response:
    metadata = json.load(response)
matches = [(filename, item) for filename, item in metadata["packages.conda"].items()
           if item["name"] == "vcomp14"]
filename, item = sorted(matches, key=lambda pair: pair[1]["timestamp"])[-1]
package_url = "https://conda.anaconda.org/conda-forge/win-64/" + filename
with urllib.request.urlopen(package_url, timeout=60) as response:
    data = response.read()
if hashlib.sha256(data).hexdigest() != item["sha256"]:
    raise ValueError("Runtime package checksum mismatch")
names = []
with zipfile.ZipFile(io.BytesIO(data)) as archive:
    payload = next(name for name in archive.namelist() if name.startswith("pkg-"))
    contents = zstd.decompress(archive.read(payload))
    with tarfile.open(fileobj=io.BytesIO(contents)) as files:
        for member in files.getmembers():
            if member.name.lower().endswith(".dll") and member.isfile():
                source = files.extractfile(member)
                binary = source.read()
                pe_offset = struct.unpack_from("<I", binary, 0x3c)[0]
                if struct.unpack_from("<H", binary, pe_offset + 4)[0] != 0x8664:
                    continue
                destination = target / Path(member.name).name
                destination.write_bytes(binary)
                names.append(destination.name)
(target / "provenance.json").write_text(json.dumps({"url": package_url,
    "sha256": item["sha256"], "files": names}, indent=2), encoding="utf-8")
print("App-local runtime:", names)
