"""Output: all violations reported, one line each; warnings prefixed."""
from .conftest import check, deployment

VOLUMES = """volumes:
                - name: data
                  persistentVolumeClaim:
                    claimName: missing"""


def test_all_violations_are_reported():
    manifest = (
        deployment(image="a:latest", name="one")
        + "---\n"
        + deployment(image="IMAGE_PLACEHOLDER", name="two")
        + "---\n"
        + deployment(image="b", name="three")
    )
    result = check(manifest)
    assert result.code == 1
    assert len(result.violations) == 3


def test_container_violation_line_format():
    result = check(deployment(image="a:latest"))
    assert result.lines == [
        '<stdin>: Deployment/app container "main": image "a:latest" resolves to '
        ":latest; pin an explicit tag or digest [no-latest-tag]"
    ]


def test_resource_violation_line_omits_container():
    result = check(deployment(image="IMAGE_PLACEHOLDER"))
    assert result.lines[0].startswith("<stdin>: Deployment/app: ")
    assert 'container "' not in result.lines[0]


def test_warnings_are_prefixed_and_do_not_change_exit_code():
    result = check(deployment(volumes=VOLUMES))
    assert result.code == 0
    assert len(result.lines) == 1
    assert result.lines[0].startswith("warning: <stdin>: Deployment/app: ")


def test_nothing_is_written_to_stdout(capsys):
    check(deployment(image="a:latest"))
    assert capsys.readouterr().out == ""
