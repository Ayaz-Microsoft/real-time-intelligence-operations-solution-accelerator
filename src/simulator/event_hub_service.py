"""Event Hub service for sending manufacturing events."""

import json
from typing import Any

try:
    from azure.eventhub import EventHubProducerClient, EventData
    from azure.identity import AzureCliCredential
except ImportError:
    print(
        "❌ Error: azure-eventhub and azure-identity packages are "
        "required."
    )
    print(
        "Install them using: "
        "pip install azure-eventhub azure-identity"
    )
    raise


class EventHubService:
    """Manages Event Hub connections and event sending."""

    def __init__(
        self,
        fully_qualified_namespace: str,
        event_hub_name: str
    ) -> None:
        """Initialize Event Hub service."""
        self.fully_qualified_namespace = fully_qualified_namespace
        self.event_hub_name = event_hub_name
        self.credential = AzureCliCredential()

    def send_event(self, data: Any) -> None:
        """Send an event to Event Hub."""
        producer = EventHubProducerClient(
            fully_qualified_namespace=self.fully_qualified_namespace,
            eventhub_name=self.event_hub_name,
            credential=self.credential
        )

        event_json = json.dumps(data)

        with producer:
            event = EventData(event_json)

            event.properties = {
                "content-type": "application/json",
                "source": "EventHubService"
            }

            producer.send_event(event)
