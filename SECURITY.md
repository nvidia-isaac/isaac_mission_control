# Isaac Mission Control Security Considerations

## Security overview and approach
Isaac provides a reference copy of Isaac Cloud Services which allows API based submission of missions to enable control of robots.  The reference is intended to work on a <b>limited access workstation</b> to demonstrate functionality.  The following document outlines security parameters to safely deploy locally, but to understand exercises needed for production deployment.

To facilitate cloud robotics control, the following local or remote web services work in concert:
- Local Services
    - Mission Control
    - Waypoint Graph Generator (SWAGGER)
    - Mission Dispatch
    - Mission Database
    - Mission Client
    - cuOpt
    - (opt) IsaacSim
- Local OSS Services
    - postgres
    - Mosquitto (MQTT)

## Containerized services
All Local Services above are provided as Docker Containers.  Through the Docker Compose file provided in the tutorial, you can understand and limit certain network access to your robotics fleet.  

## VDA5050 / MQTT 
Isaac Cloud Services at the lowest level uses VDA5050 over MQTT for robot control.  Examples provided do not leverage or demonstrate any MQTT authorization / encyption attempts and are not secured.  Examples should be run on a limited access trusted network.  For further information on securing VDA5050 and MQTT, one can start here: [VDA5050 Specification](https://github.com/VDA5050/VDA5050/blob/main/VDA5050_EN.md#-62-mqtt-connection-handling-security-and-qos)

## Postgres
Postgres is used by Mission Dispatch and Mission Database to store the state of a mission, state of robots, and facilitate state management for VDA5050.  The default implementation provided is to use username/password.  A production environment should access via encrypted channel, restrict user access via eg (OIDC), among other standard postgres security practices.  Please evaluate the network access parameters provided in the tutorial docker compose to ensure they are compatible with your organization's security policies.

## Mission Dispatch/Database
Mission Dispatch and Mission Database do not provide authorization / authentication to API endpoints.  Arbitrary users on the evaluation workstation can submit missions or impersonate robots.  External access to the Mission Dispatch and Database services should be limited to the local workstation. 

## Mission Control 
Mission Control does not provide authorization / authentication to API endpoints.  Arbitrary users on the evaluation workstation can submit missions.  External access to the Mission Control services should be limited to the local workstation.
