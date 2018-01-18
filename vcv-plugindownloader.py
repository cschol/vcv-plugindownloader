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

__version__ = "2.1.0"


COMMUNITY_REPO = "https://github.com/VCVRack/community.git"
COMMUNITY_REPO_DIR = os.path.join(os.getcwd(), "community")
DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")
FAILED_CHECKSUM_DIR = os.path.join(DOWNLOAD_DIR, "failed_checksum")


# Certain plugins require special branches, tags, or shas to be checked out to build successfully.
PLUGIN_COMMITTISH_MAP = {
    "Fundamental": "v0.5.1"
}


def download_from_url(url, target_path=os.getcwd()):
    file_name = os.path.basename(url).split('?')[0]
    request = urllib.request.Request(url, headers={'User-Agent': 'vcv-plugindownloader/%s' % __version__}) 
    opener = urllib.request.build_opener()
    with opener.open(request) as response, open(os.path.join(target_path, file_name), 'wb') as out_file:
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
    parser.add_argument("-l", "--list", nargs='+', help="list of plugins to download (white-space separated)")
    parser.add_argument("-x", "--exclude", nargs='+', help="list of plugins to exclude from download (white-space separated)")
    parser.add_argument("-s", "--source", action='store_true', help="attempt to build plugins from source if binary release is not available", default=False)
    parser.add_argument("-j", "--jobs", type=int, help="number of jobs to pass to make command via -j option", default=1)
    parser.add_argument("-c", "--clean", action='store_true', help="clean plugin build via 'make clean'", default=False)

    return parser.parse_args()


def get_source_dir(plugin_name):
    return os.path.join(os.getcwd(), plugin_name.replace(" ", "_")+".git")


def clone_source(plugin_name, git_repo_url):
    try:
        subprocess.check_call(["git", "clone", git_repo_url, os.path.basename(get_source_dir(plugin_name))], cwd=os.path.join(os.getcwd()))
    except Exception as e:
        print("[%s] ERROR: Failed to clone source" % plugin_name)
        raise e


def check_out_revision(plugin_name, committish):
    try:
        subprocess.check_call(["git", "checkout", committish], cwd=get_source_dir(plugin_name))
    except Exception as e:
        print("[%s] ERROR: Failed to check out revision" % plugin_name)
        raise e


def update_source(plugin_name, git_repo_url, fetch_only=False):
    try:
        subprocess.check_call(["git", "fetch", "--all"], cwd=get_source_dir(plugin_name))
        if not fetch_only:
            subprocess.check_call(["git", "merge", "origin/master"], cwd=get_source_dir(plugin_name))
    except Exception as e:
        print("[%s] ERROR: Failed to update source" % plugin_name)
        raise e


def build_source(plugin_name, num_jobs=1):
    try:
        subprocess.check_call(["make", "-j%s" % num_jobs], cwd=get_source_dir(plugin_name))
    except Exception as e:
        print("[%s] ERROR: Failed to build from source" % plugin_name)
        raise e


def get_latest_git_tag(plugin_name):
    try:
        output = subprocess.check_output(["git", "describe", "--abbrev=0", "--tags"], cwd=get_source_dir(plugin_name))
        return output.strip().decode("UTF-8")
    except Exception as e:
        print("[%s] ERROR: Failed to determine git tag" % plugin_name)
        return None


def clean_build(plugin_name):
    try:
        subprocess.check_call(["make", "clean"], cwd=get_source_dir(plugin_name))
    except Exception as e:
        print("[%s] ERROR: Failed to clean build" % plugin_name)
        raise e


def main(argv=None):

    args = parse_args(argv)

    platform = args.platform
    plugin_list = args.list
    plugin_exclude_list = args.exclude
    build_from_source = args.source
    num_jobs = args.jobs
    do_clean = args.clean
   
    PLATFORM_STRING = {"win": "Windows", "mac": "MacOS", "lin": "Linux"}

    print("VCV Plugin Downloader v%s" % __version__)
    print("Platform: %s" % PLATFORM_STRING[platform])

    error_list = []

    try:
        # 'community' repository contains all of the plugin information.
        print("Updating community repository...")
        if not os.path.exists(COMMUNITY_REPO_DIR):
            subprocess.check_call(["git", "clone", COMMUNITY_REPO]  )
        else:
            subprocess.check_call(["git", "pull"], cwd=COMMUNITY_REPO_DIR)
        
        # Build a list of plugins to download.
        plugins_json = []
        # Any plugins specified on command line?
        if plugin_list:
            for l in plugin_list:
                p = glob.glob(os.path.join(COMMUNITY_REPO_DIR, "plugins/%s.json" % l))
                if not p:
                    print("[%s] ERROR: Invalid plugin name" % l)
                else:
                    plugins_json.append(p[0])
        else:
            # Grab all .json files in the plugins directory.
            plugins_json = glob.glob(os.path.join(COMMUNITY_REPO_DIR, "plugins/*.json"))

        # Filter out any excluded plugins (if applicable)
        if plugin_exclude_list:
            plugins_json = [p for p in plugins_json if not any(x for x in plugin_exclude_list if x == os.path.basename(p).strip(".json"))]
        
        if not plugins_json:
            print("ERROR: No valid plugins found")
            return 1

        # Housekeeping
        if not os.path.exists(DOWNLOAD_DIR):
            os.mkdir(DOWNLOAD_DIR)
        if os.path.exists(FAILED_CHECKSUM_DIR):
            shutil.rmtree(FAILED_CHECKSUM_DIR)

        #
        # Process all plugins in our assemble list.
        #
        for plugin in plugins_json:
            with open(plugin) as json_data:
                pj = json.load(json_data)

                slug = pj['slug']
                version = pj['version'] if "version" in pj.keys() else "UNKNOWN VERSION"

                print("[%s] Version %s" % (slug, version))

                download = True
                extract = True
                build = build_from_source

                #
                # Binary release available to download?
                #
                if "downloads" in pj:
                    #
                    # Binary release available for the selected platform?
                    #
                    if platform in pj["downloads"].keys():
                        url = pj["downloads"][platform]["download"]
                        file_name = os.path.basename(url).split('?')[0]
                        sha256 = pj["downloads"][platform]["sha256"] if "sha256" in pj["downloads"][platform].keys() else None
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
                                download_from_url(url, DOWNLOAD_DIR)
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
                        module_dir = os.path.join(os.getcwd(), zipfile.ZipFile(download_file).namelist()[0])
                        
                        if os.path.exists(module_dir):
                            # If we downloaded the module, replace the current version with the new one.
                            if download:
                                shutil.rmtree(module_dir)
                            else:
                                extract = False

                        if extract:
                            print("[%s] Extracting..." % slug, end='', flush=True)
                            try:
                                with zipfile.ZipFile(download_file) as z:
                                    z.extractall(os.getcwd())
                                print("OK")
                            except Exception as e:
                                print("ERROR: Failed to extract module: %s" % e)
                                if os.path.exists(module_dir):
                                    shutil.rmtree(module_dir)
                                error_list.append(slug)
                                continue

                        # Plugin downloaded and extracted successfully. No need to build from source.
                        build = False
                    
                    #
                    # No binary release available for selected platform
                    #
                    else:
                        print("[%s] WARNING: Binary archive download for platform %s not available" % (slug, PLATFORM_STRING[platform]))

                #
                # No binary release download exists
                #
                else:
                    print("[%s] WARNING: No binary archive downloads available in repository" % slug)

                #
                # Build plugin from source?
                #
                if build:
                    source_url = pj["source"] if "source" in pj.keys() else None
                    
                    #
                    # Source code URL in the plugin file?
                    #
                    if source_url:
                        # Clone the repo if it does not exist.
                        if not os.path.exists(get_source_dir(slug)):
                            print("[%s] Cloning plugin source..." % slug)
                            clone_source(slug, source_url)
                        else:
                            # Fetch updates for local repository.
                            # Skip updating working copy since we might be on a detached head.
                            update_source(slug, source_url, fetch_only=True)

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

                        if committish:
                            print("[%s] Checking out revision: %s"  % (slug, committish))
                            check_out_revision(slug, committish)
                        
                        if do_clean:
                            print("[%s] Cleaning build..." % slug)
                            clean_build(slug)

                        print("[%s] Building plugin..." % slug)
                        try:
                            build_source(slug, num_jobs)
                        except Exception as e:
                            error_list.append(slug)
                    #
                    # No source code provided. Can't build.
                    #
                    else:
                        print("[%s] No source URL specified in JSON file. Skipping." % slug)
        
        if error_list:
            print("")
            print("PLUGINS WITH ERRORS: %s" % " ".join(error_list))
            return 1

        return 0

    except Exception as e:
        print("Exception: %s" % e)
        traceback.print_exc(file=sys.stderr)
        return 1    

if __name__ == "__main__":
    sys.exit(main(sys.argv))
