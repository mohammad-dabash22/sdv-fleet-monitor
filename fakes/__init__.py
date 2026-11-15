"""Fake stand-ins for the external tools, for the one-process demo and the tests.

    fakes.kuksa  -> stands in for kuksa_client.grpc (the Kuksa Databroker client)
    fakes.zenoh  -> stands in for the zenoh library (vehicle-to-cloud transport)
    fakes.pubsub -> stands in for google.cloud.pubsub_v1.PublisherClient (the V1 bridge)

They copy the parts of the real APIs that our code uses, so the vehicle and
cloud code is the same with the real tools. Only these small factory files choose
between fake and real:

    vehicle/common/databroker.py  (Kuksa)
    vehicle/common/transport.py   (Zenoh, vehicle side)
    cloud/app/transport.py        (Zenoh, cloud side)
    cloud/pipeline/pubsub.py      (Pub/Sub)

The real tools: DATABROKER=kuksa, TRANSPORT=zenoh, PUBSUB=gcp. The fakes keep the unit tests fast
without a running Databroker, Zenoh router or Pub/Sub.
"""
