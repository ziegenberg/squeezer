import pytest
import os
import sys
import json
import ansible_runner


TEST_NAMES = [
    name[:-5] for name in os.listdir("tests/playbooks") if name.endswith(".yaml")
]

IGNORED_WARNINGS = []


# Clean environment from anything that could cause encoding problems
if sys.version_info[0] == 2:
    for envvar in os.environ.keys():
        try:
            os.environ[envvar] = (
                os.environ[envvar].decode("utf-8").encode("ascii", "ignore")
            )
        except UnicodeError:
            os.environ.pop(envvar)


def run_playbook_vcr(
    tmpdir, test_name, extra_vars=None, record=False, check_mode=False
):
    if extra_vars is None:
        extra_vars = {}
    limit = None
    if record:
        # Cassettes that are to be overwritten must be deleted first
        record_mode = "once"
        extra_vars["recording"] = True
    else:
        # Never reach out to the internet
        record_mode = "none"
        # Only run the tests (skip fixtures)
        limit = "tests"

    # Dump recording parameters to json-file and pass its name by environment
    test_params = {
        "test_name": test_name,
        "serial": 0,
        "record_mode": record_mode,
        "check_mode": check_mode,
    }
    params_file = tmpdir.join("test_params_{}.json".format(test_name))
    params_file.write(json.dumps(test_params))
    os.environ["PAM_TEST_VCR_PARAMS_FILE"] = params_file.strpath
    os.environ["XDG_CACHE_HOME"] = tmpdir.join("cache").strpath
    return run_playbook(
        test_name, extra_vars=extra_vars, limit=limit, check_mode=check_mode
    )


def run_playbook(test_name, extra_vars=None, limit=None, check_mode=False):
    # Assemble parameters for playbook call
    playbook = test_name + ".yaml"
    os.environ["ANSIBLE_CONFIG"] = os.path.join(os.getcwd(), "ansible.cfg")
    kwargs = {}
    kwargs["playbook"] = os.path.join(os.getcwd(), "tests", "playbooks", playbook)
    kwargs["inventory"] = os.path.join(os.getcwd(), "tests", "inventory", "hosts")
    kwargs["verbosity"] = 4
    if extra_vars:
        kwargs["extravars"] = extra_vars
    if limit:
        kwargs["limit"] = limit
    if check_mode:
        kwargs["cmdline"] = "--check"
    return ansible_runner.run(**kwargs)


@pytest.mark.parametrize("test_name", TEST_NAMES)
def test_playbook(tmpdir, test_name, vcrmode, pulp_container_log):
    if vcrmode == "live":
        run = run_playbook(test_name)
    else:
        record = vcrmode == "record"
        run = run_playbook_vcr(tmpdir, test_name, record=record)
    assert run.rc == 0

    for event in run.events:
        event_warnings = [
            warning
            for warning in event.get("event_data", {})
            .get("res", {})
            .get("warnings", [])
            if warning not in IGNORED_WARNINGS
        ]
        assert [] == event_warnings, str(event_warnings)


@pytest.mark.parametrize("test_name", TEST_NAMES)
def test_check_mode(tmpdir, test_name, vcrmode):
    assert vcrmode == "replay", "Check-mode tests only work in replay."
    # if test_name == 'not_working_one':
    #     pytest.skip("TODO: Fix check_mode test for not_working_one.")
    run = run_playbook_vcr(tmpdir, test_name, check_mode=True)
    assert run.rc == 0
