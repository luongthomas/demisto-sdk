import os
import io
import re
import glob
import json
import shutil
import zipfile
from typing import List
import yaml
import yamlordereddictloader

from demisto_sdk.commands.unify.unifier import Unifier
from demisto_sdk.commands.common.tools import get_child_directories, get_child_files, print_warning, \
    get_yml_paths_in_dir, print_error
from demisto_sdk.commands.common.git_tools import get_current_working_branch
from demisto_sdk.commands.common.constants import INTEGRATIONS_DIR, MISC_DIR, PLAYBOOKS_DIR, REPORTS_DIR,\
    DASHBOARDS_DIR, WIDGETS_DIR, SCRIPTS_DIR, INCIDENT_FIELDS_DIR, CLASSIFIERS_DIR, LAYOUTS_DIR, CONNECTIONS_DIR, \
    BETA_INTEGRATIONS_DIR, INDICATOR_FIELDS_DIR, INCIDENT_TYPES_DIR, TEST_PLAYBOOKS_DIR, PACKS_DIR, DIR_TO_PREFIX, \
    TOOLS_DIR


class ContentCreator:

    def __init__(self, artifacts_path: str, content_version='', content_bundle_path='',
                 test_bundle_path='', packs_bundle_path='', preserve_bundles=False):
        self.artifacts_path = artifacts_path if artifacts_path else '/home/circleci/project/artifacts'
        self.content_version = content_version
        self.preserve_bundles = preserve_bundles

        # temp folder names
        self.content_bundle = content_bundle_path if content_bundle_path else os.path.join(self.artifacts_path,
                                                                                           'bundle_content')
        self.test_bundle = test_bundle_path if test_bundle_path else os.path.join(self.artifacts_path,
                                                                                  'bundle_test')
        self.packs_bundle = packs_bundle_path if packs_bundle_path else os.path.join(self.artifacts_path,
                                                                                     'bundle_packs')

        # directories in which content resides
        self.content_directories = [
            BETA_INTEGRATIONS_DIR,
            CLASSIFIERS_DIR,
            CONNECTIONS_DIR,
            DASHBOARDS_DIR,
            INCIDENT_FIELDS_DIR,
            INCIDENT_TYPES_DIR,
            INDICATOR_FIELDS_DIR,
            INTEGRATIONS_DIR,
            LAYOUTS_DIR,
            MISC_DIR,
            PLAYBOOKS_DIR,
            REPORTS_DIR,
            SCRIPTS_DIR,
            WIDGETS_DIR,
        ]

        self.packages_to_skip = []
        self.packs_to_skip = ['ApiModules']  # See the pack README

        # zip files names (the extension will be added later - shutil demands file name without extension)
        self.content_zip = os.path.join(self.artifacts_path, 'content_new')
        self.test_zip = os.path.join(self.artifacts_path, 'content_test')
        self.packs_zip = os.path.join(self.artifacts_path, 'content_packs')

        # server can't handle long file names
        self.file_name_max_size = 85
        self.long_file_names = []  # type:List

    def run(self):
        """Runs the content creator and returns the appropriate status code for the operation.

        Returns:
            int. 1 for failure, 0 for success.
        """
        self.create_content()
        if self.long_file_names:
            print_error(f'The following files exceeded to file name length limit of {self.file_name_max_size}:\n'
                        f'{json.dumps(self.long_file_names, indent=4)}')
            return 1

        return 0

    def create_unifieds_and_copy(self, package_dir, dest_dir='', skip_dest_dir=''):
        """
        For directories that have packages, aka subdirectories for each integration/script
        e.g. "Integrations", "Beta_Integrations", "Scripts". Creates a unified yml and writes
        it to the dest_dir

        Arguments:
            package_dir: (str)
                Path to directory in which there are package subdirectories. e.g. "Integrations",
                "Beta_Integrations", "Scripts"
            dest_dir: (str)
                Path to destination directory to which the unified yml for a package should be written
            skip_dest_dir: (str)
                Path to the directory to which the unified yml for a package should be written in the
                case the package is part of the skipped list
        """
        dest_dir = dest_dir if dest_dir else self.content_bundle
        skip_dest_dir = skip_dest_dir if skip_dest_dir else self.test_bundle

        scanned_packages = glob.glob(os.path.join(package_dir, '*/'))
        package_dir_name = os.path.basename(package_dir)
        for package in scanned_packages:
            ymls, _ = get_yml_paths_in_dir(package, error_msg='')
            if not ymls or (len(ymls) == 1 and ymls[0].endswith('_unified.yml')):
                msg = 'Skipping package: {} -'.format(package)
                if not ymls:
                    print_warning('{} No yml files found in the package directory'.format(msg))
                else:
                    print_warning('{} Only unified yml found in the package directory'.format(msg))
                continue
            unification_tool = Unifier(package, package_dir_name, dest_dir)
            if any(package_to_skip in package for package_to_skip in self.packages_to_skip):
                # there are some packages that we don't want to include in the content zip
                # for example HelloWorld integration
                unification_tool = Unifier(package, package_dir_name, skip_dest_dir)
                print('skipping {}'.format(package))
            unification_tool.merge_script_package_to_yml()

    @staticmethod
    def add_tools_to_bundle(bundle):
        for directory in glob.glob(os.path.join(TOOLS_DIR, '*')):
            zipf = zipfile.ZipFile(os.path.join(bundle, f'tools-{os.path.basename(directory)}.zip'), 'w',
                                   zipfile.ZIP_DEFLATED)
            zipf.comment = b'{ "system": true }'
            for root, _, files in os.walk(directory):
                for file_name in files:
                    zipf.write(os.path.join(root, file_name), file_name)
            zipf.close()

    def copy_playbook_yml(self, path, out_path, *args):
        """
        Add "playbook-" prefix to playbook file's copy destination filename if it wasn't already present
        """
        dest_dir_path = os.path.dirname(out_path)
        dest_file_name = os.path.basename(out_path)
        if not dest_file_name.startswith('playbook-'):
            new_name = '{}{}'.format('playbook-', dest_file_name)
            out_path = os.path.join(dest_dir_path, new_name)
        shutil.copyfile(path, out_path)

    def copy_content_yml(self, path, out_path, yml_info):
        """
        Copy content ymls (except for playbooks) to the out_path (presumably a bundle)
        """
        parent_dir_name = os.path.basename(os.path.dirname(path))
        if parent_dir_name in DIR_TO_PREFIX and not os.path.basename(path).startswith('playbook-'):
            script_obj = yml_info
            if parent_dir_name != SCRIPTS_DIR:
                script_obj = yml_info['script']
            with io.open(path, mode='r', encoding='utf-8') as file_:
                yml_data = yaml.load(file_, Loader=yamlordereddictloader.SafeLoader)
            unifier = Unifier(os.path.dirname(path), parent_dir_name, out_path)
            out_map = unifier.write_yaml_with_docker(yml_data, yml_info, script_obj)
            if len(out_map.keys()) > 1:
                print(" - yaml generated multiple files: {}".format(out_map.keys()))
            return
        # not a script or integration file. Simply copy
        shutil.copyfile(path, out_path)

    def copy_dir_yml(self, dir_path, bundle):
        """
        Copy the yml files inside a directory to a bundle.

        :param dir_path: source directory
        :param bundle: destination bundle
        :return: None
        """
        scan_files, _ = get_yml_paths_in_dir(dir_path, error_msg='')
        content_files = 0
        dir_name = os.path.basename(dir_path)
        copy_func = self.copy_playbook_yml if dir_name in ['Playbooks', 'TestPlaybooks'] else self.copy_content_yml
        for path in scan_files:
            if len(os.path.basename(path)) >= self.file_name_max_size:
                self.long_file_names.append(path)

            with open(path, 'r') as file_:
                yml_info = yaml.safe_load(file_)

            ver = yml_info.get('fromversion', '0')
            print(f' - processing: {ver} ({path})')
            copy_func(path, os.path.join(bundle, os.path.basename(path)), yml_info)
            content_files += 1
        print(f' - total files: {content_files}')

    def copy_dir_json(self, dir_path, bundle):
        """
        Copy the json files inside a directory to a bundle.

        :param dir_path: source directory
        :param bundle: destination bundle
        :return: None
        """
        # handle *.json files
        dir_name = os.path.basename(dir_path)
        scan_files = glob.glob(os.path.join(dir_path, '*.json'))
        for path in scan_files:
            dpath = os.path.basename(path)
            if dir_name == 'IncidentTypes':
                if not dpath.startswith('incidenttype-'):
                    dpath = f'incidenttype-{dpath}'
            # this part is a workaround because server doesn't support indicatorfield-*.json naming
            if dir_name in ['IndicatorFields', 'IncidentFields']:
                if not dpath.startswith('incidentfield-'):
                    dpath = f'incidentfield-{dpath}'
            new_path = dpath
            if dir_name == 'IndicatorFields' and not dpath.startswith('incidentfield-indicatorfield-'):
                new_path = dpath.replace('incidentfield-', 'incidentfield-indicatorfield-')
            if os.path.isfile(os.path.join(bundle, new_path)):
                raise NameError(
                    f'Failed while trying to create {os.path.join(bundle, new_path)}. File already exists.'
                )
            dpath = new_path

            if len(dpath) >= self.file_name_max_size:
                self.long_file_names.append(os.path.basename(dpath))

            shutil.copyfile(path, os.path.join(bundle, dpath))

    def copy_dir_files(self, *args):
        """
        Copy the yml and json files from inside a directory to a bundle.

        :param args: (source directory, destination bundle)
        :return: None
        """
        # handle *.json files
        self.copy_dir_json(*args)
        # handle *.yml files
        self.copy_dir_yml(*args)

    def copy_test_files(self, test_playbooks_dir=TEST_PLAYBOOKS_DIR):
        """
        Copy test playbook ymls to the test bundle.

        :param test_playbooks_dir:
        :return: None
        """
        print('Copying test files to test bundle')
        scan_files = glob.glob(os.path.join(test_playbooks_dir, '*'))
        for path in scan_files:
            if os.path.isdir(path):
                non_circle_tests = glob.glob(os.path.join(path, '*'))
                for new_path in non_circle_tests:
                    print(f'copying path {new_path}')
                    shutil.copyfile(new_path, os.path.join(self.test_bundle, os.path.basename(new_path)))

            else:
                print(f'Copying path {path}')
                shutil.copyfile(path, os.path.join(self.test_bundle, os.path.basename(path)))

    def copy_packs_content_to_old_bundles(self, packs):
        """
        Copy relevant content (yml and json files) from packs to the appropriate bundle. Test playbooks to the
        bundle that gets zipped to 'content_test.zip' and the rest of the content to the bundle that gets zipped to
        'content_new.zip'. Adds file prefixes where necessary according to how server expects to ingest the files.
        """
        for pack in packs:
            if os.path.basename(pack) in self.packs_to_skip:
                continue
            # each pack directory has it's own content subdirs, 'Integrations',
            # 'Scripts', 'TestPlaybooks', 'Layouts' etc.
            sub_dirs_paths = get_child_directories(pack)
            for sub_dir_path in sub_dirs_paths:
                dir_name = os.path.basename(sub_dir_path)
                if dir_name == 'TestPlaybooks':
                    self.copy_test_files(sub_dir_path)
                else:
                    # handle one-level deep content
                    self.copy_dir_files(sub_dir_path, self.content_bundle)
                    if dir_name in DIR_TO_PREFIX:
                        # then it's a directory with nested packages that need to be handled
                        # handle nested packages
                        self.create_unifieds_and_copy(sub_dir_path)

    def copy_packs_content_to_packs_bundle(self, packs):
        """
        Copy content in packs to the bundle that gets zipped to 'content_packs.zip'. Preserves directory structure
        except that packages inside the "Integrations" or "Scripts" directory inside a pack are flattened. Adds file
        prefixes according to how server expects to ingest the files, e.g. 'integration-' is prepended to integration
        yml filenames and 'script-' is prepended to script yml filenames and so on and so forth.
        """
        for pack in packs:
            pack_name = os.path.basename(pack)
            if pack_name in self.packs_to_skip:
                continue
            pack_dst = os.path.join(self.packs_bundle, pack_name)
            os.mkdir(pack_dst)
            pack_dirs = get_child_directories(pack)
            pack_files = get_child_files(pack)
            # copy first level pack files over
            for file_path in pack_files:
                shutil.copy(file_path, os.path.join(pack_dst, os.path.basename(file_path)))
            # handle content directories in the pack
            for content_dir in pack_dirs:
                dir_name = os.path.basename(content_dir)
                dest_dir = os.path.join(pack_dst, dir_name)
                os.mkdir(dest_dir)
                if dir_name in DIR_TO_PREFIX:
                    packages_dirs = get_child_directories(content_dir)
                    for package_dir in packages_dirs:
                        ymls, _ = get_yml_paths_in_dir(package_dir, error_msg='')
                        if not ymls or (len(ymls) == 1 and ymls[0].endswith('_unified.yml')):
                            msg = 'Skipping package: {} -'.format(package_dir)
                            if not ymls:
                                print_warning('{} No yml files found in the package directory'.format(msg))
                            else:
                                print_warning('{} Only unified yml found in the package directory'.format(msg))
                            continue
                        package_dir_name = os.path.basename(package_dir)
                        unifier = Unifier(package_dir, dir_name, dest_dir)
                        unifier.merge_script_package_to_yml()

                        # also copy CHANGELOG markdown files over (should only be one per package)
                        package_files = get_child_files(package_dir)
                        changelog_files = [
                            file_path
                            for file_path in package_files if 'CHANGELOG.md' in file_path
                        ]
                        for md_file_path in changelog_files:
                            md_out_name = '{}-{}_CHANGELOG.md'.format(DIR_TO_PREFIX.get(dir_name), package_dir_name)
                            shutil.copyfile(md_file_path, os.path.join(dest_dir, md_out_name))
                else:
                    self.copy_dir_files(content_dir, dest_dir)

    @staticmethod
    def update_content_version(content_ver: str = '', path: str = './Scripts/CommonServerPython/CommonServerPython.py'):
        regex = r'CONTENT_RELEASE_VERSION = .*'
        if not content_ver:
            try:
                with open('content-descriptor.json') as file_:
                    descriptor = json.load(file_)
                content_ver = descriptor['release']
            except (FileNotFoundError, json.JSONDecodeError, KeyError):
                print_error('Invalid descriptor file. make sure file content is a valid json with "release" key.')
                return

        try:
            with open(path, 'r+') as file_:
                content = file_.read()
                content = re.sub(regex, f"CONTENT_RELEASE_VERSION = '{content_ver}'", content, re.M)
                file_.seek(0)
                file_.write(content)
        except Exception as ex:
            print_warning(f'Could not open CommonServerPython File - {ex}')

    @staticmethod
    def update_branch(path: str = './Scripts/CommonServerPython/CommonServerPython.py'):

        regex = r'CONTENT_BRANCH_NAME = .*'
        branch_name = get_current_working_branch()
        try:
            with open(path, 'r+') as file_:
                content = file_.read()
                content = re.sub(regex, f"CONTENT_BRANCH_NAME = '{branch_name}'", content, re.M)
                file_.seek(0)
                file_.write(content)
        except Exception as ex:
            print_warning(f'Could not open CommonServerPython File - {ex}')

        return branch_name

    def create_content(self):
        """
        Creates the content artifact zip files "content_test.zip", "content_new.zip", and "content_packs.zip"
        """
        # update content_version in commonServerPython
        self.update_content_version(self.content_version)
        branch_name = self.update_branch()
        print(f'Updated CommonServerPython with branch {branch_name} and content version {self.content_version}')
        print('Starting to create content artifact...')

        try:
            print('creating dir for bundles...')
            for bundle_dir in [self.content_bundle, self.test_bundle, self.packs_bundle]:
                os.mkdir(bundle_dir)

            self.add_tools_to_bundle(self.content_bundle)

            for package_dir in DIR_TO_PREFIX:
                # handles nested package directories
                self.create_unifieds_and_copy(package_dir)

            for content_dir in self.content_directories:
                print(f'Copying dir {content_dir} to bundles...')
                self.copy_dir_files(content_dir, self.content_bundle)

            self.copy_test_files()

            # handle copying packs content to bundles for zipping to content_new.zip and content_test.zip
            packs = get_child_directories(PACKS_DIR)
            self.copy_packs_content_to_old_bundles(packs)

            # handle copying packs content to packs_bundle for zipping to `content_packs.zip`
            self.copy_packs_content_to_packs_bundle(packs)

            print('Copying content descriptor to content and test bundles')
            for bundle_dir in [self.content_bundle, self.test_bundle]:
                shutil.copyfile('content-descriptor.json', os.path.join(bundle_dir, 'content-descriptor.json'))

            for doc_file in ('./Documentation/doc-CommonServer.json', './Documentation/doc-howto.json'):
                if os.path.exists(doc_file):
                    print(f'copying {doc_file} doc to content bundle')
                    shutil.copyfile(doc_file,
                                    os.path.join(self.content_bundle, os.path.basename(doc_file)))
                else:
                    print_warning(f'{doc_file} was not found and '
                                  'therefore was not added to the content bundle')

            print('Compressing bundles...')
            shutil.make_archive(self.content_zip, 'zip', self.content_bundle)
            shutil.make_archive(self.test_zip, 'zip', self.test_bundle)
            shutil.make_archive(self.packs_zip, 'zip', self.packs_bundle)
            shutil.copyfile("./Tests/id_set.json", os.path.join(self.artifacts_path, "id_set.json"))
            if os.path.exists('release-notes.md'):
                print('copying release-notes.md to artifacts directory "{}"'.format(self.artifacts_path))
                shutil.copyfile('release-notes.md', os.path.join(self.artifacts_path, 'release-notes.md'))
            else:
                print_warning('release-notes.md was not found in the content directory and therefore not '
                              'copied over to the artifacts directory')
            print(f'finished creating the content artifacts at "{os.path.abspath(self.artifacts_path)}"')
        finally:
            if not self.preserve_bundles:
                if os.path.exists(self.content_bundle):
                    shutil.rmtree(self.content_bundle)
                if os.path.exists(self.test_bundle):
                    shutil.rmtree(self.test_bundle)
                if os.path.exists(self.packs_bundle):
                    shutil.rmtree(self.packs_bundle)
