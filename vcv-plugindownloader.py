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

__version__ = "1.0.0"

COMMUNITY_REPO = "https://github.com/VCVRack/community.git"
COMMUNITY_REPO_DIR = os.path.join(os.getcwd(), "community")
DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")
FAILED_CHECKSUM_DIR = os.path.join(DOWNLOAD_DIR, "failed_checksum")


def download_url(url, target_path=os.getcwd()):
    file_name = os.path.basename(url).split('?')[0]
    with urllib.request.urlopen(url) as response, open(os.path.join(target_path, file_name), 'wb') as out_file:
        shutil.copyfileobj(response, out_file)


def hash_sha256(file_name):
    hash_sha256 = hashlib.sha256()
    with open(file_name, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_sha256.update(chunk)
    return hash_sha256.hexdigest()


def main(args=None):

    if len(args) != 2:
        print("Usage: %s [win|mac|lin]" % args[0])
        return 1

    platform = args[1]
    if platform != "win" and platform != "mac" and platform != "lin":
        print("ERROR: Unsupported platform")
        return 1
    platform_string = "Windows" if platform == "win" else "MacOS" if platform == "mac" else "Linux"

    print("VCV Plugin Downloader v%s" % __version__)
    print("Platform: %s" % platform_string)

    try:
        print("Updating community repository...")
        if not os.path.exists(COMMUNITY_REPO_DIR):
            subprocess.check_call(["git", "clone", COMMUNITY_REPO]  )
        else:
            subprocess.check_call(["git", "pull"], cwd=COMMUNITY_REPO_DIR)
        
        plugins_json = glob.glob(os.path.join(COMMUNITY_REPO_DIR, "plugins/*.json"))
        if not plugins_json:
            print("ERROR: No plugins found in community repository")
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
                                download_url(url, DOWNLOAD_DIR)
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
                        print("[%s] WARNING: Binary archive download for platform %s not available" % (name, platform_string))
                else:
                    print("[%s] WARNING: No binary archive downloads available in repository" % name)
        return 0

    except Exception as e:
        print("Exception: %s" % e)
        return 1    

if __name__ == "__main__":
    sys.exit(main(sys.argv))
