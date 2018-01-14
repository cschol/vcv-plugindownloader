# vcv-plugindownloader

This simple script parses the plugin information provided by the VCV Rack [community repository](https://github.com/VCVRack/community)
and download the plugins available for the specified target platform (Windows, MacOS, Linux).

The script

- clones/updates the `community` repository for access to the latest plugin information.
- downloads the archive, verifies the `sha256`, and extracts the archive.
- discards any archives that fail `sha256` verification (or encounter any other error) and does **not** extract the archive.
- only downloads archives that are not already present in the `downloads` directory (verified via `sha256`).
- only updates the local version of the plugin if a new version was downloaded.

## Prerequisites

- Python 3
- git

## Usage

- Clone this repository to VCV Rack's `plugins` directory

- Execute the script with the appropriate **target platform**

*Windows* example (in `MinGW64` shell):
```
cd ~/src/Rack/plugins
./vcv-plugindownloader/vcv-plugindownloader.py win
```

Valid target platforms are: `win`, `mac`, `lin`.

**NOTE:** The script always assumes the **current working directory** is the `plugins` directory! 

## Supported platforms

The script has been tested on the Windows platform, but **should** work on MacOS and Linux.
