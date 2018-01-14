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


__version__ = "1.1.0"


COMMUNITY_REPO = "https://github.com/VCVRack/community.git"
COMMUNITY_REPO_DIR = os.path.join(os.getcwd(), "community")
DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")
FAILED_CHECKSUM_DIR = os.path.join(DOWNLOAD_DIR, "failed_checksum")


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

    return parser.parse_args()


def main(argv=None):

    args = parse_args(argv)

    platform = args.platform
    plugin_list = args.list

    PLATFORM_STRING = {"win": "Windows", "mac": "MacOS", "lin": "Linux"}

    print("VCV Plugin Downloader v%s" % __version__)
    print("Platform: %s" % PLATFORM_STRING[platform])

    try:
        print("Updating community repository...")
        if not os.path.exists(COMMUNITY_REPO_DIR):
            subprocess.check_call(["git", "clone", COMMUNITY_REPO]  )
        else:
            subprocess.check_call(["git", "pull"], cwd=COMMUNITY_REPO_DIR)
        
        plugins_json = []
        if plugin_list:
            for l in plugin_list:
                p = glob.glob(os.path.join(COMMUNITY_REPO_DIR, "plugins/%s.json" % l))
                if not p:
                    print("[%s] ERROR: Invalid plugin name" % l)
                else:
                    plugins_json.append(p[0])
        else:
            plugins_json = glob.glob(os.path.join(COMMUNITY_REPO_DIR, "plugins/*.json"))

        if not plugins_json:
            print("ERROR: No valid plugins found in community repository")
            return 1

        if not os.path.exists(DOWNLOAD_DIR):
            os.mkdir(DOWNLOAD_DIR)
        if os.path.exists(FAILED_CHECKSUM_DIR):
            shutil.rmtree(FAILED_CHECKSUM_DIR)

        for plugin in plugins_json:
            with open(plugin) as json_data:
                pj = json.load(json_data)

                name = pj['name']
                version = pj['version'] if "version" in pj.keys() else "UNKNOWN VERSION"

                print("[%s] Version %s" % (name, version))

                download = False
                extract = False

                if "downloads" in pj:
                    if platform in pj["downloads"].keys():
                        url = pj["downloads"][platform]["download"]
                        file_name = os.path.basename(url).split('?')[0]
                        sha256 = pj["downloads"][platform]["sha256"] if "sha256" in pj["downloads"][platform].keys() else None
                        
                        download_file = os.path.join(DOWNLOAD_DIR, file_name)
                            
                        if os.path.exists(download_file):
                            if not sha256:
                                print("[%s] ERROR: Missing SHA256 checksum in .json file! Skipping module." % name)
                                download = False

                            # If there is a checksum mismatch, download the archive.
                            if sha256 != hash_sha256(download_file):
                                os.remove(download_file)
                                download = True
                            else:
                                print("[%s] Already at newest version. Skipping download." % name)
                                download = False
                        else:
                            download = True

                        if download:
                            try:
                                print("[%s] Downloading version %s..." % (name, version), end='', flush=True)
                                download_from_url(url, DOWNLOAD_DIR)
                            except Exception as e:
                                print("ERROR: Failed to download archive for %s: %s" % (name, e))
                                continue

                            def move_failed_file():
                                if not os.path.exists(FAILED_CHECKSUM_DIR):
                                    os.mkdir(FAILED_CHECKSUM_DIR)
                                shutil.move(download_file, os.path.join(FAILED_CHECKSUM_DIR, file_name))

                            if not sha256:
                                print("ERROR: Missing SHA256 checksum in .json file!")
                                move_failed_file()
                                continue

                            if sha256 != hash_sha256(download_file):
                                print("ERROR: Checksum verification failed!")
                                move_failed_file()
                                continue
                            else:
                                print("OK")

                        module_dir = os.path.join(os.getcwd(), zipfile.ZipFile(download_file).namelist()[0])
                        
                        if os.path.exists(module_dir):
                            # If we downloaded the module, replace the current version with the new one.
                            if download:
                                shutil.rmtree(module_dir)
                                extract = True
                            else:
                                extract = False
                        else:
                            extract = True

                        if extract:
                            print("[%s] Extracting..." % name, end='', flush=True)
                            try:
                                with zipfile.ZipFile(download_file) as z:
                                    z.extractall(os.getcwd())
                                print("OK")
                            except Exception as e:
                                print("ERROR: Failed to extract module: %s" % e)
                                if os.path.exists(module_dir):
                                    shutil.rmtree(module_dir)
                    else:
                        print("[%s] WARNING: Binary archive download for platform %s not available" % (name, PLATFORM_STRING[platform]))
                else:
                    print("[%s] WARNING: No binary archive downloads available in repository" % name)
        return 0

    except Exception as e:
        print("Exception: %s" % e)
        traceback.print_exc(file=sys.stderr)
        return 1    

if __name__ == "__main__":
    sys.exit(main(sys.argv))
