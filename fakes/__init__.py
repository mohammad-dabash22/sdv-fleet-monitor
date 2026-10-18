"""Fake stand-ins for the external tools we do not run yet.

    fakes.kuksa  -> stands in for kuksa_client.grpc (the Kuksa Databroker client)
    fakes.zenoh  -> stands in for the zenoh library (vehicle-to-cloud transport)

They copy the parts of the real APIs that our code uses, so the vehicle and
cloud code does not change when the real tools arrive. Only the two small
factory files choose between fake and real:

    vehicle/common/databroker.py  (Kuksa)
    vehicle/common/transport.py   (Zenoh, vehicle side)
    cloud/app/transport.py        (Zenoh, cloud side)

NEXT PHASE: set TRANSPORT=zenoh and DATABROKER=kuksa. Keep this package for
fast unit tests that do not need a running Databroker or Zenoh router.
"""
