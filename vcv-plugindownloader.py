#!/usr/bin/env python3

import sys
import os
import json
import glob
import urllib.request
import shutil
import zipfile
import hashlib
import subprocess
import argparse
import traceback
import getpass

__version__ = "2.7.0"

DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")
FAILED_CHECKSUM_DIR = os.path.join(DOWNLOAD_DIR, "failed_checksum")
PLATFORM_STRING = {"win": "Windows", "mac": "MacOS", "lin": "Linux"}
RACK_API_HOST = "https://api.vcvrack.com"

# Certain plugins require special branches, tags, or shas to be checked out to build successfully.
PLUGIN_COMMITTISH_MAP = {
    "Fundamental": "v0.5.1",
    "mscHack": "master"
}

def check_git():
    try:
        subprocess.check_output(["git", "--version"])
        return True
    except Exception as e:
        print("git is not available on this system: %s" % e)
        return False


def download_from_url(url, target_path):
    assert url
    assert target_path
    request = urllib.request.Request(url, headers={'User-Agent': 'vcv-plugindownloader/%s' % __version__})
    opener = urllib.request.build_opener()
    with opener.open(request) as response, open(target_path, 'wb') as out_file:
        shutil.copyfileobj(response, out_file)


def hash_sha256(file_name):
    hash_sha256 = hashlib.sha256()
    with open(file_name, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_sha256.update(chunk)
    return hash_sha256.hexdigest()


def parse_args(argv):
    parser = argparse.ArgumentParser()

    parser.add_argument("platform", help="platform to download plugins for", type=str, choices=["win", "mac", "lin"])
    parser.add_argument("-i", "--include", nargs='+', help="list of plugins to include in download (white-space separated)")
    parser.add_argument("-x", "--exclude", nargs='+', help="list of plugins to exclude from download (white-space separated)")
    parser.add_argument("-s", "--source", action='store_true', help="attempt to build plugins from source if binary release is not available", default=False)
    parser.add_argument("-j", "--jobs", type=int, help="number of jobs to pass to make command via -j option", default=1)
    parser.add_argument("-c", "--clean", action='store_true', help="clean plugin build via 'make clean'", default=False)
    parser.add_argument("-d", "--delete", action='store_true', help="delete plugins from plugins directory. Use with caution!", default=False)
    parser.add_argument("-y", "--yes", action='store_true', help="assume 'yes' as the answer to any question asked by the script", default=False)
    parser.add_argument("-l", "--list", action='store_true', help="list all available plugins", default=False)
    parser.add_argument("-p", "--patch", type=str, help="name of patch file to download plugins for")
    parser.add_argument("--prefer-source", action='store_true', help="prefer building plugin source over downloading binaries even if binaries are available", default=False)
    parser.add_argument("-u", "--update", action='store_true', help="update all existing plugins found in the plugins directory", default=False)

    return parser.parse_args()


def get_source_dir(plugin_name):
    return os.path.join(os.getcwd(), plugin_name.replace(" ", "_")+".git")


def clone_source(plugin_name, git_repo_url):
    try:
        subprocess.check_call(["git", "clone", git_repo_url, os.path.basename(get_source_dir(plugin_name))], cwd=os.getcwd())
    except Exception as e:
        print("[%s] ERROR: Failed to clone source: %s" % (plugin_name, e))
        raise e

def update_submodules(plugin_name):
    try:
        subprocess.check_call(["git", "submodule", "update", "--init", "--recursive"], cwd=get_source_dir(plugin_name))
    except Exception as e:
        print("[%s] ERROR: Failed to update submodule: %s" % (plugin_name, e))
        raise e


def check_out_revision(plugin_name, committish):
    try:
        subprocess.check_call(["git", "checkout", committish], cwd=get_source_dir(plugin_name))
    except Exception as e:
        print("[%s] ERROR: Failed to check out revision: %s" % (plugin_name, e))
        raise e


def update_source(plugin_name, git_repo_url, fetch_only=False):
    try:
        subprocess.check_call(["git", "fetch", "--all"], cwd=get_source_dir(plugin_name))
        if not fetch_only:
            subprocess.check_call(["git", "merge", "origin/master"], cwd=get_source_dir(plugin_name))
    except Exception as e:
        print("[%s] ERROR: Failed to update source: %s" % (plugin_name, e))
        raise e


def build_source(plugin_name, num_jobs=4):
    try:
        subprocess.check_call(["make", "-j%s" % num_jobs], cwd=get_source_dir(plugin_name))
    except Exception as e:
        print("[%s] ERROR: Failed to build from source: %s" % (plugin_name, e))
        raise e


def get_latest_git_tag(plugin_name):
    try:
        output = subprocess.check_output(["git", "describe", "--abbrev=0", "--tags"], cwd=get_source_dir(plugin_name))
        return output.strip().decode("UTF-8")
    except Exception:
        print("[%s] WARNING: Could not determine git tag" % plugin_name)
        return None


def clean_build(plugin_name):
    try:
        subprocess.check_call(["make", "clean"], cwd=get_source_dir(plugin_name))
    except Exception as e:
        print("[%s] ERROR: Failed to clean build: %s" % (plugin_name, e))
        raise e


def api_request(url, payload=None):
    assert url
    req = "%s%s" % (url, "" if not payload else "?%s" % urllib.parse.urlencode(payload))
    return urllib.request.urlopen(req).read().decode('utf-8')


def get_community_plugins():
    return json.loads(api_request(RACK_API_HOST+"/community/plugins", None))


def get_plugins_from_patch_file(patch_file):
    plugins = set()
    with open(patch_file, 'r') as pf:
        try:
            patch_json = json.loads(pf.read())
            plugins = set([x["plugin"] for x in patch_json["modules"]])
        except KeyError:
            print("ERROR: No plugins found in patch file '%s" % patch_file)
            # Empty patch
        except json.decoder.JSONDecodeError as e:
            print("ERROR: Invalid patch file '%s': %s" % (patch_file, e))
    return sorted(plugins)


def main(argv=None):

    # Argument handling
    args = parse_args(argv)

    platform = args.platform
    plugin_include_list = args.include
    plugin_exclude_list = args.exclude
    build_from_source = args.source
    prefer_source = args.prefer_source
    num_jobs = args.jobs
    do_clean = args.clean
    delete = args.delete
    assume_yes = args.yes
    list_plugins = args.list
    patch_file = args.patch
    do_update = args.update

    print("VCV Plugin Downloader v%s" % __version__)
    print("Platform: %s" % PLATFORM_STRING[platform])
    print("")

    update_list = []
    error_list = []
    warning_list = []

    git_available = check_git()

    if not git_available and build_from_source:
        print("ERROR: Building from source requires 'git' to be installed. Aborting.")
        return 1

    if patch_file:
        if not os.path.exists(patch_file) or not patch_file.endswith(".vcv"):
            print("ERROR: Invalid patch file: '%s'. Aborting." % patch_file)
            return 1

    community_plugins = get_community_plugins()["plugins"]
    available_plugins = sorted([p["slug"] for p in community_plugins])

    try:
        # Print list of available plugins
        if list_plugins:
            print("Available plugins in Community repository:")
            print(", ".join([p["slug"] for p in community_plugins]))
            return 0

        # Build a list of plugins to download.
        plugins = []

        # If update is specified on command line, get list of plugins in plugins directory.
        if do_update:
            p_list = sorted([p.split(".")[0] for p in os.listdir(os.getcwd()) if p.split(".")[0] in available_plugins])
            for pl in p_list:
                plugins.append([p for p in community_plugins if p["slug"] == pl][0])

        # If patch file is specified on command line, get the list of plugins from the patch.
        elif patch_file:
            patch_plugins = get_plugins_from_patch_file(patch_file)

            # Filter out certain Rack stock plugins, that we don't want to download.
            patch_plugins = [p for p in patch_plugins if not p in ["Core", "Fundamental"]]

            if not patch_plugins:
                print("No plugins to download for patch file '%s'" % patch_file)
                return 0

            print("Modules found in patch file '%s':" % patch_file)
            print(", ".join(patch_plugins))
            print("")

            for pp in patch_plugins:
                if pp not in available_plugins:
                    print("[%s] ERROR: Plugin not found in Community repository. Skipping." % pp)
                plugins.append([p for p in community_plugins if p["slug"] == pp][0])

        # Any plugins specified on command line?
        elif plugin_include_list:
            for pi in plugin_include_list:
                if pi not in available_plugins:
                    print("[%s] ERROR: Invalid plugin name" % pi)
                    return 1
                plugins.append([p for p in community_plugins if p["slug"] == pi][0])

        # Assume to download ALL plugins from community repository.
        else:
            plugins = community_plugins

        # Filter out any excluded plugins (if applicable)
        if plugin_exclude_list:
            for px in plugin_exclude_list:
                if px not in available_plugins:
                    print("[%s] ERROR: Invalid plugin name" % px)
                    return 1
            plugins = [p for p in plugins if not any(x for x in plugin_exclude_list if x == p["slug"])]

        # Housekeeping
        if not os.path.exists(DOWNLOAD_DIR):
            os.mkdir(DOWNLOAD_DIR)
        if os.path.exists(FAILED_CHECKSUM_DIR):
            shutil.rmtree(FAILED_CHECKSUM_DIR)

        # Confirm deletion (if requested).
        if delete and not assume_yes:
            print("Are you sure you want to DELETE the following plugins?\n")
            print(" ".join(p["slug"] for p in plugins))
            confirm = input("\nPlease confirm [yes|no]: ")
            if confirm.lower() not in ["yes", "no"]:
                print("Invalid choice. Aborting.")
                return 1
            if confirm.lower() != "yes":
                print("Delete cancelled.")
                return 0

        #
        # Process all plugins in our assembled list.
        #
        for plugin in plugins:

            slug = plugin['slug']
            version = plugin['version'] if "version" in plugin.keys() else "UNKNOWN VERSION"

            print("[%s] Version %s" % (slug, version))

            download = True
            extract = True
            build = build_from_source

            #
            # Plugin deletion requested?
            #
            if delete:

                # TODO Remove this when all plugins are adhering to plugin conventions.
                # Some plugins have directory names that do not match the slug.
                plugin_root = ""
                if "downloads" in plugin and platform in plugin["downloads"].keys():
                    file_name = os.path.basename(plugin["downloads"][platform]["download"]).split('?')[0]
                    plugin_zip = os.path.join(DOWNLOAD_DIR, file_name)
                    try:
                        plugin_root = zipfile.ZipFile(plugin_zip).namelist()[0].strip(os.sep)
                    except FileNotFoundError:
                        pass

                delete_dir = set([plugin_root, slug, slug+".git"]) & set(os.listdir(os.getcwd()))
                if delete_dir:
                    delete_dir = list(delete_dir)[0] # convert from set()
                    print("[%s] Deleting plugin directory '%s'..." % (slug, delete_dir), end='', flush=True)
                    try:
                        shutil.rmtree(os.path.join(os.getcwd(), delete_dir))
                        print("OK")
                    except Exception as e:
                        print("ERROR: Failed to remove plugin: %s" % e)
                else:
                    print("[%s] ERROR: Plugin directory not found" % slug)
                continue

            #
            # Skip binary download if building source is preferred.
            #
            if prefer_source:
                pass
            #
            # Binary release available to download?
            #
            elif "downloads" in plugin:
                #
                # Binary release available for the selected platform?
                #
                if platform in plugin["downloads"].keys():
                    url = plugin["downloads"][platform]["download"]
                    file_name = os.path.basename(url).split('?')[0]
                    sha256 = plugin["downloads"][platform]["sha256"] if "sha256" in plugin["downloads"][platform].keys() else None
                    download_file = os.path.join(DOWNLOAD_DIR, file_name)

                    #
                    # If downloaded artifact exists already, check if it is the latest version (based on SHA256)
                    #
                    if os.path.exists(download_file):
                        if not sha256:
                            print("[%s] ERROR: Missing SHA256 checksum in .json file! Skipping module." % slug)
                            download = False

                        # If there is a checksum mismatch, there must be a new version
                        # (or the current one is corrupt). Download the archive.
                        if sha256 != hash_sha256(download_file):
                            os.remove(download_file)
                        else:
                            print("[%s] Already at newest version. Skipping download." % slug)
                            download = False

                    #
                    # Do we need to download a (potentially newer) version of the plugin?
                    #
                    if download:
                        try:
                            print("[%s] Downloading version %s..." % (slug, version), end='', flush=True)
                            target_path = os.path.join(DOWNLOAD_DIR, os.path.basename(url).split('?')[0])
                            download_from_url(url, target_path)
                        except Exception as e:
                            print("ERROR: Failed to download archive for %s: %s" % (slug, e))
                            error_list.append(slug)
                            continue

                        def move_failed_file():
                            if not os.path.exists(FAILED_CHECKSUM_DIR):
                                os.mkdir(FAILED_CHECKSUM_DIR)
                            shutil.move(download_file, os.path.join(FAILED_CHECKSUM_DIR, file_name))
                            error_list.append(slug)

                        if not sha256:
                            print("ERROR: Missing SHA256 checksum in .json file!")
                            move_failed_file()
                            continue

                        checksum = hash_sha256(download_file)
                        if sha256 != checksum:
                            print("ERROR: Checksum verification failed")
                            print("expected: %s" % sha256)
                            print("actual:   %s" % checksum)
                            move_failed_file()
                            continue
                        else:
                            print("OK")

                    #
                    # Update local (extracted) version of the plugin?
                    #
                    plugin_root = zipfile.ZipFile(download_file).namelist()[0].strip("/\\")
                    plugin_path = os.path.join(os.getcwd(), plugin_root)

                    # Check if plugin adheres to plugin naming conventions.
                    # Some modules have directory names that do not match the slug.
                    if plugin_root != slug:
                        print("[%s] WARNING: Plugin root folder does not match slug: %s" % (slug, plugin_root))
                        warning_list.append(slug)

                    if os.path.exists(plugin_path):
                        # If we downloaded the module, replace the current version with the new one.
                        if download:
                            shutil.rmtree(plugin_path)
                        else:
                            extract = False

                    if extract:
                        print("[%s] Extracting..." % slug, end='', flush=True)
                        try:
                            with zipfile.ZipFile(download_file) as z:
                                z.extractall(os.getcwd())
                            print("OK")
                            update_list.append(slug)
                        except Exception as e:
                            print("ERROR: Failed to extract module: %s" % e)
                            if os.path.exists(plugin_path):
                                shutil.rmtree(plugin_path)
                            error_list.append(slug)
                            continue

                    # Plugin downloaded and extracted successfully. No need to build from source.
                    build = False

                #
                # No binary release available for selected platform
                #
                else:
                    print("[%s] Binary archive download for platform %s not available." % (slug, PLATFORM_STRING[platform]))

            #
            # No binary release download exists
            #
            else:
                print("[%s] No binary archive downloads available in repository." % slug)

            #
            # Build plugin from source?
            #
            if build:
                source_url = plugin["source"] if "source" in plugin.keys() else None

                #
                # Source code URL in the plugin file?
                #
                if source_url:
                    try:
                        # Clone the repo if it does not exist.
                        if not os.path.exists(get_source_dir(slug)):
                            print("[%s] Cloning plugin source..." % slug)
                            clone_source(slug, source_url)
                        else:
                            # Fetch updates for local repository.
                            # Skip updating working copy since we might be on a detached head.
                            update_source(slug, source_url, fetch_only=True)

                        # Update git submodules (if applicable)
                        if os.path.exists(os.path.join(get_source_dir(slug), ".gitmodules")):
                            print("[%s] Updating submodules..." % slug)
                            update_submodules(slug)

                        # Prepare the repository for building. That means either
                        #  - a hard-coded sha/tag OR
                        #  - the latest git tag OR
                        #  - the HEAD of the master branch
                        committish = PLUGIN_COMMITTISH_MAP[slug] if slug in PLUGIN_COMMITTISH_MAP.keys() else None
                        if not committish:
                            committish = get_latest_git_tag(slug)
                            if not committish:
                                print("[%s] Updating plugin source..." % slug)
                                check_out_revision(slug, "master")
                                update_source(slug, source_url)
                                committish = "HEAD"

                        print("[%s] Checking out revision: %s"  % (slug, committish))
                        check_out_revision(slug, committish)

                        if do_clean:
                            print("[%s] Cleaning build..." % slug)
                            clean_build(slug)

                        print("[%s] Building plugin..." % slug)
                        build_source(slug, num_jobs)

                        update_list.append(slug)

                    except Exception:
                        error_list.append(slug)
                #
                # No source code provided. Can't build.
                #
                else:
                    print("[%s] No source URL specified in JSON file. Skipping." % slug)

        # Remove annoying "__MACOSX" directory for all non-Mac platforms, if it exists.
        annoying_mac_dir = os.path.join(os.getcwd(), "__MACOSX")
        if platform != "mac" and os.path.exists(annoying_mac_dir):
            shutil.rmtree(annoying_mac_dir)

        if update_list:
            print("")
            print("PLUGINS UPDATED: %s" % ", ".join(update_list))

        if error_list:
            print("")
            print("PLUGINS WITH ERRORS: %s" % ", ".join(error_list))

        if warning_list:
            print("")
            print("PLUGINS WITH WARNINGS: %s" % ", ".join(warning_list))

        if error_list:
            return 1
        if warning_list:
            return 2

        return 0

    except Exception as e:
        print("Exception: %s" % e)
        traceback.print_exc(file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv))
