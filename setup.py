"""Packages the cloud code for the Dataflow workers (spec REQ-033 AC3, REQ-037).

tools/dataflow_job.py passes --setup_file=./setup.py, so each worker installs the `cloud` package
(the Beam graph, validate(), the trip math and the Store with its SQL schema) and the PostgreSQL
driver. Nothing else in the repository uses this file.
"""

from setuptools import find_packages, setup

setup(
    name="sdv-fleet-pipeline",
    version="1.0.0",
    packages=find_packages(include=["cloud", "cloud.*"], exclude=["cloud.tests", "cloud.tests.*"]),
    package_data={"cloud": ["db/*.sql", "pipeline/schemas/*.json"]},
    install_requires=["psycopg2-binary==2.9.13"],
)
