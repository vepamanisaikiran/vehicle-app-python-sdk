# Copyright (c) 2022 Robert Bosch GmbH and Microsoft Corporation
#
# This program and the accompanying materials are made available under the
# terms of the Apache License, Version 2.0 which is available at
# https://www.apache.org/licenses/LICENSE-2.0.
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
#
# SPDX-License-Identifier: Apache-2.0

"""A sample Velocitas vehicle app for adjusting seat position."""

# pylint: disable=C0103, C0413, E1101

import asyncio
import json
import logging
import signal

from sdv_model import Vehicle, vehicle  # type: ignore

from sdv.util.log import (  # type: ignore
    get_opentelemetry_log_factory,
    get_opentelemetry_log_format,
)
from sdv.vdb.subscriptions import DataPointReply
from sdv.vehicle_app import VehicleApp, subscribe_topic

logging.setLogRecordFactory(get_opentelemetry_log_factory())
logging.basicConfig(format=get_opentelemetry_log_format())
logging.getLogger().setLevel("INFO")
logger = logging.getLogger(__name__)


class SeatAdjusterApp(VehicleApp):
    """
    Sample Velocitas Vehicle App.

    The SeatAdjusterApp subscribes to a MQTT topic to listen for incoming
    requests to change the seat position and calls the SeatService to move the seat
    upon such a request, but only if Vehicle.Speed equals 0.

    It also subcribes to the VehicleDataBroker for updates of the
    Vehicle.Cabin.Seat.Row1.Pos1.Position signal and publishes this
    information via another specific MQTT topic
    """

    def __init__(self, vehicle_client: Vehicle):
        super().__init__()
        self.Vehicle = vehicle_client

    async def on_start(self):
        """Run when the vehicle app starts"""
        await self.Vehicle.Cabin.Seat.Row(1).Pos(1).Position.subscribe(
            self.on_seat_position_changed
        )

    async def on_seat_position_changed(self, data: DataPointReply):
        response_topic = "seatadjuster/currentPosition"
        await self.publish_event(
            response_topic,
            json.dumps(
                {
                    "position": data.get(
                        self.Vehicle.Cabin.Seat.Row(1).Pos(1).Position
                    ).value
                }
            ),
        )

    @subscribe_topic("seatadjuster/mqttNative/request")
    async def mqttnative_request_received(self, data_str: str) -> None:
        data = json.loads(data_str)
        response_topic = "seatadjuster/mqttNative/response"
        response_data = {"requestId": data["requestId"], "result": {}}
        await self.publish_event(response_topic, json.dumps(response_data))

    @subscribe_topic("seatadjuster/setPosition/request")
    async def on_set_position_request_received(self, data_str: str) -> None:
        data = json.loads(data_str)
        response_topic = "seatadjuster/setPosition/response"
        response_data = {"requestId": data["requestId"], "result": {}}

        vehicle_speed = (await self.Vehicle.Speed.get()).value

        position = data["position"]
        if vehicle_speed == 0:
            try:
                await self.Vehicle.Cabin.Seat.Row1.Pos1.Position.set(position)
                response_data["result"] = {
                    "status": 0,
                    "message": f"Set Seat position to: {position}",
                }
            except ValueError as error:
                response_data["result"] = {
                    "status": 1,
                    "message": f"Failed to set the position {position}, error: {error}",
                }
            except Exception:
                response_data["result"] = {
                    "status": 1,
                    "message": "Exception on set Seat position",
                }

        else:
            error_msg = f"""Not allowed to move seat because vehicle speed
                is {vehicle_speed} and not 0"""
            response_data["result"] = {"status": 1, "message": error_msg}

        await self.publish_event(response_topic, json.dumps(response_data))


async def main():

    """Main function"""
    logger.info("Starting seat adjuster app...")
    seat_adjuster_app = SeatAdjusterApp(vehicle)
    await seat_adjuster_app.run()

LOOP = asyncio.get_event_loop()
LOOP.add_signal_handler(signal.SIGTERM, LOOP.stop)
LOOP.run_until_complete(main())
LOOP.close()
