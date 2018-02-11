# vcv-plugindownloader

This simple script parses the plugin information provided by the VCV Rack [community repository](https://github.com/VCVRack/community)
and download the **binary release** versions of plugins available for the specified target platform (Windows, MacOS, Linux).
If a binary release is not available, an option can be provided on the command line to fall back on building the plugin from source.

The script

- gets the latest plugin information from the *Rack Web API*, which is synced to the community repository on GitHub.
- downloads the archive of **binary releases**, verifies the `sha256`, and extracts the archive.
- discards any archives that fail `sha256` verification (or encounter any other error) and does **not** extract the archive.
- only downloads archives that are not already present in the `downloads` directory (verified via `sha256`).
- only updates the local version of the plugin if a new version was downloaded.
- can fall back to cloning and building the plugin from source (via command line option).
- will try prefer the latest `git tag` (if there is one), otherwise check out the `HEAD` of the `master` branch to build the plugin.

## Prerequisites

- Command line access (i.e. a shell)

**NOTE for Windows users**: Using the Windows `cmd.exe` will work for downloading binaries, but most likely fail for building plugins from source.
An [msys2](http://www.msys2.org/) development environment with the appropriate Unix-like shell is recommended for building plugins
from source using the `-s` (or `--source`) option of this script.

- Python 3

Optional:

- git (only required for building plugins from source)

## Usage

- Clone this repository to VCV Rack's `plugins` directory **OR** download the script from `Github`

**IMPORTANT NOTE**:
For **binary** packages the `plugins` directory can refer to either the directory inside of the *source tree* for **dev builds**, e.g. `~/source/Rack/plugins`, or
the **platform-specific** plugin directory for **installed VCV Rack versions**, e.g. `Documents/Rack/` (Mac), `My Documents/Rack/` (Windows), or `~/.Rack/` (Linux).
If you decide to use the `-s` (or `--source`) option to fall back to compiling plugins from source that are not available for your platform
in binary form, the script **must** be executed from the plugins directory in the *source tree*, e.g. `~/source/Rack/plugins`.


- Change script permissions appropriately per your platform (only required on Linux and MacOS)

For example on `Linux`:

```
chmod +x vcv-plugindownloader.py
```

- Execute the script with the appropriate **target platform**

```
vcv-plugindownloader.py win
```

**NOTE:** The script always assumes the **current working directory** is the `plugins` directory!

### Arguments

- The *required* platform argument selects the platform, for which plugins are downloaded.

Valid platforms are: `win`, `mac`, `lin`.

- The *optional* `-l` (or `--list`) argument prints out the names of all available plugins in the community repository:

```
vcv-plugindownloader.py win --list
```

- The *optional* `-i` (or `--include`) argument allows specifying individual plugins to include in the download in a *whitespace-separated* list:

```
vcv-plugindownloader.py win -i AudibleInstruments Grayscale
```

- The *optional* `-x` (or `--exclude`) argument allows specifying individual plugins to exclude from download in a *whitespace-separated* list:

```
vcv-plugindownloader.py win -x AudibleInstruments Grayscale
```

- The *optional* `-s` (or `--source`) argument attempts to fall back on cloning and building the plugin from source:

```
vcv-plugindownloader.py win -s
vcv-plugindownloader.py win -s -l Fundamental
```

- The *optional* `-j` (or `--jobs`) argument specifies number of jobs to pass to `make` with the `-j` argument:

```
vcv-plugindownloader.py win -s -l Fundamental -j 8
```

Obviously only has an effect when `-s` is specified.

- The *optional* `-c` (or `--clean`) argument specifies whether to clean the build directory before compiling from source (via `make clean`):

```
vcv-plugindownloader.py win -s -c -l Fundamental
```

Obviously only has an effect when `-s` is specified.

- The *optional* `-d` (or `--delete`) argument allows deleting plugins from the `plugins` folder:

```
vcv-plugindownloader.py win -d
vcv-plugindownloader.py win -d -l Fundamental
```

**USE WITH CAUTION!**

Executing `vcv-plugindownloader.py win -d` will delete **ALL** Windows plugins in your `plugin` directory!
The script will *confirm* the `delete` action, unless `--yes` is specified on the command line to override the confirmation dialog.

- The *optional* `-y` (or `--yes`) argument answers all questions with 'yes':

```
vcv-plugindownloader.py win --delete --yes
```

**USE WITH CAUTION!**

This will override any dialog and answer all questions with **yes**. Useful for automated tasks.

### Notes

For certain modules (e.g. Fundamental), a git `branch` or `tag` needs to be checked out for the build to succeed
(`master` is not compatible with the currently release tag).
This `branch` or `tag` is hard-coded in the script and will be updated as required. Note, that plugins that are
pinned like that will not be updated automatically.

## Supported platforms

The script has been tested on the Windows platform, but **should** work on MacOS and Linux.
