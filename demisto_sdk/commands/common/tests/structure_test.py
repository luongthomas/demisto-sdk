import os
from os.path import isfile
from shutil import copyfile
from typing import List, Tuple

import pytest
import yaml

from demisto_sdk.commands.common.constants import DIR_LIST
from demisto_sdk.commands.common.hook_validations.structure import StructureValidator
from demisto_sdk.tests.constants_test import VALID_TEST_PLAYBOOK_PATH, INVALID_PLAYBOOK_PATH, \
    VALID_INTEGRATION_TEST_PATH, VALID_INTEGRATION_ID_PATH, INVALID_INTEGRATION_ID_PATH, VALID_PLAYBOOK_ID_PATH, \
    INVALID_PLAYBOOK_ID_PATH, VALID_LAYOUT_PATH, INVALID_LAYOUT_PATH, INVALID_WIDGET_PATH, \
    VALID_WIDGET_PATH, VALID_DASHBOARD_PATH, INVALID_DASHBOARD_PATH, LAYOUT_TARGET, \
    DASHBOARD_TARGET, WIDGET_TARGET, PLAYBOOK_TARGET, INTEGRATION_TARGET, INCIDENT_FIELD_TARGET, PLAYBOOK_PACK_TARGET, \
    INDICATORFIELD_EXACT_SCHEME, INDICATORFIELD_EXTRA_FIELDS, INDICATORFIELD_MISSING_AND_EXTRA_FIELDS, \
    INDICATORFIELD_MISSING_FIELD


class TestStructureValidator:
    INPUTS_TARGETS = [
        LAYOUT_TARGET,
        DASHBOARD_TARGET,
        WIDGET_TARGET,
        PLAYBOOK_TARGET,
        INTEGRATION_TARGET,
        INCIDENT_FIELD_TARGET,
        PLAYBOOK_PACK_TARGET,
    ]
    CREATED_DIRS = list()  # type: List

    @classmethod
    def setup_class(cls):
        # checking that the files in the test are not exists so they won't overwrites.
        for target in cls.INPUTS_TARGETS:
            if isfile(target) is True:
                pytest.fail(f"{target} File in tests already exists!")
        # Creating directory for tests if they're not exists
        for directory in DIR_LIST:
            if not os.path.exists(directory):
                cls.CREATED_DIRS.append(directory)
                os.mkdir(directory)

    @classmethod
    def teardown_class(cls):
        for target in cls.INPUTS_TARGETS:
            if isfile(target) is True:
                os.remove(target)
        for directory in cls.CREATED_DIRS:
            if os.path.exists(directory):
                os.rmdir(directory)

    SCHEME_VALIDATION_INPUTS = [
        (VALID_TEST_PLAYBOOK_PATH, 'playbook', True, "Found a problem in the scheme although there is no problem"),
        (INVALID_PLAYBOOK_PATH, 'playbook', False, "Found no problem in the scheme although there is a problem"),
    ]

    @pytest.mark.parametrize("path, scheme, answer, error", SCHEME_VALIDATION_INPUTS)
    def test_scheme_validation_playbook(self, path, scheme, answer, error, mocker):
        mocker.patch.object(StructureValidator, 'scheme_of_file_by_path', return_value=scheme)
        validator = StructureValidator(file_path=path)
        assert validator.is_valid_scheme() is answer, error

    SCHEME_VALIDATION_INDICATORFIELDS = [
        (INDICATORFIELD_EXACT_SCHEME, INCIDENT_FIELD_TARGET, True),
        (INDICATORFIELD_EXTRA_FIELDS, INCIDENT_FIELD_TARGET, True),
        (INDICATORFIELD_MISSING_FIELD, INCIDENT_FIELD_TARGET, False),
        (INDICATORFIELD_MISSING_AND_EXTRA_FIELDS, INCIDENT_FIELD_TARGET, False)
    ]

    @pytest.mark.parametrize("path, scheme, answer", SCHEME_VALIDATION_INDICATORFIELDS)
    def test_scheme_validation_indicatorfield(self, path, scheme, answer, mocker):
        validator = StructureValidator(file_path=path, predefined_scheme='incidentfield')
        assert validator.is_valid_scheme() is answer

    INPUTS_VALID_FROM_VERSION_MODIFIED = [
        (VALID_TEST_PLAYBOOK_PATH, INVALID_PLAYBOOK_PATH, False),
        (INVALID_PLAYBOOK_PATH, VALID_PLAYBOOK_ID_PATH, False),
        (INVALID_PLAYBOOK_PATH, INVALID_PLAYBOOK_PATH, True)
    ]

    @pytest.mark.parametrize('path, old_file_path, answer', INPUTS_VALID_FROM_VERSION_MODIFIED)
    def test_fromversion_update_validation_yml_structure(self, path, old_file_path, answer):
        validator = StructureValidator(file_path=path)
        with open(old_file_path) as f:
            validator.old_file = yaml.safe_load(f)
            assert validator.is_valid_fromversion_on_modified() is answer

    INPUTS_IS_ID_MODIFIED = [
        (INVALID_PLAYBOOK_PATH, VALID_PLAYBOOK_ID_PATH, True, "Didn't find the id as updated in file"),
        (VALID_PLAYBOOK_ID_PATH, VALID_PLAYBOOK_ID_PATH, False, "Found the ID as changed although it is not")
    ]

    @pytest.mark.parametrize("current_file, old_file, answer, error", INPUTS_IS_ID_MODIFIED)
    def test_is_id_modified(self, current_file, old_file, answer, error):
        validator = StructureValidator(file_path=current_file)
        with open(old_file) as f:
            validator.old_file = yaml.safe_load(f)
            assert validator.is_id_modified() is answer, error

    POSITIVE_ERROR = "Didn't find a slash in the ID even though it contains a slash."
    NEGATIVE_ERROR = "found a slash in the ID even though it not contains a slash."
    INPUTS_IS_FILE_WITHOUT_SLASH = [
        (VALID_INTEGRATION_ID_PATH, True, POSITIVE_ERROR),
        (INVALID_INTEGRATION_ID_PATH, False, NEGATIVE_ERROR),
        (VALID_PLAYBOOK_ID_PATH, True, POSITIVE_ERROR),
        (INVALID_PLAYBOOK_ID_PATH, False, NEGATIVE_ERROR)

    ]

    @pytest.mark.parametrize('path, answer, error', INPUTS_IS_FILE_WITHOUT_SLASH)
    def test_integration_file_with_valid_id(self, path, answer, error):
        validator = StructureValidator(file_path=path)
        assert validator.is_file_id_without_slashes() is answer, error

    INPUTS_IS_PATH_VALID = [
        ("Reports/report-sade.json", True),
        ("Notinregex/report-sade.json", False),
        ("Packs/Test/Integrations/Cymon/Cymon.yml", True),
    ]

    @pytest.mark.parametrize('path, answer', INPUTS_IS_PATH_VALID)
    def test_is_valid_file_path(self, path, answer, mocker):
        mocker.patch.object(StructureValidator, "load_data_from_file", return_value=None)
        structure = StructureValidator(path)
        structure.scheme_name = None
        assert structure.is_valid_file_path() is answer

    INPUTS_IS_VALID_FILE = [
        (VALID_LAYOUT_PATH, LAYOUT_TARGET, True),
        (INVALID_LAYOUT_PATH, LAYOUT_TARGET, False),
        (INVALID_WIDGET_PATH, WIDGET_TARGET, False),
        (VALID_WIDGET_PATH, WIDGET_TARGET, True),
        (VALID_DASHBOARD_PATH, DASHBOARD_TARGET, True),
        (INVALID_DASHBOARD_PATH, DASHBOARD_TARGET, False),
        (VALID_TEST_PLAYBOOK_PATH, PLAYBOOK_TARGET, True),
        (VALID_INTEGRATION_TEST_PATH, INTEGRATION_TARGET, True),
        (INVALID_PLAYBOOK_PATH, INTEGRATION_TARGET, False),
    ]  # type: List[Tuple[str, str, bool]]

    @pytest.mark.parametrize('source, target, answer', INPUTS_IS_VALID_FILE)
    def test_is_file_valid(self, source, target, answer):
        try:
            copyfile(source, target)
            structure = StructureValidator(target)
            assert structure.is_valid_file() is answer
        finally:
            os.remove(target)
