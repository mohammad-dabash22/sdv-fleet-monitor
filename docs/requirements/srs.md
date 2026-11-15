<!--
Converted from "2 SRS_SDV_Fleet_Operations_Hazard_Monitor.pdf" (Version 1.0, October 4, 2026) on 2026-11-14.
The wording is unchanged. This file is the source of the FR-x and NFR-x ids that specs/ link to.
Do not edit requirements here: record any change or deviation in specs/, with the reason.
-->

# Software Requirements Specification: SDV Fleet Operations & Hazard Monitor

**Group 5:** Ahmad Musleh · Giancarlo Sotelo Lajo · Mohammad Dabash
**Version:** 1.0
**Date:** October 4, 2026

---

## 1. Introduction

### 1.1 Purpose

This document specifies the software requirements for the SDV Fleet Operations & Hazard Monitor system. It defines what the system must do (functional requirements) and the qualities it must have (non-functional requirements.

### 1.2 Scope

The SDV Fleet Operations & Hazard Monitor is a cloud-based system that monitors a simulated fleet of software-defined vehicles (SDVs). Each vehicle has a digital twin that is updated with sensor data such as speed, location, battery/fuel level, engine status and hazard events. The vehicle collects and sends this data to the cloud using Eclipse SDV tools (Kuksa, Velocitas, Ankaios, Zenoh). The cloud stores and processes the data, and a web dashboard shows the live fleet status, hazard alerts and performance to fleet operators. The system is built and deployed automatically through a CI/CD pipeline.

This document covers the full project, across both phases:

- **Phase 1 (The core stack):** digital twins, hazard detection, vehicle-to-cloud communication, vehicle software management, cloud ingestion and storage, a first dashboard, and CI/CD.
- **Phase 2 (Extensions to the core stack):** data quality checks, anomaly detection, route-efficiency analysis, and an extended dashboard. No new tools are introduced in Phase 2.

Out of scope: real vehicles or vehicle hardware, vehicle-to-vehicle communication, and mobile applications.

### 1.3 Definitions, Acronyms and Abbreviations

| Term | Meaning |
|---|---|
| SDV | Software-Defined Vehicle |
| VSS | Vehicle Signal Specification – the vehicle data model used by Kuksa |
| CI/CD | Continuous Integration / Continuous Deployment |
| Digital Twin | A virtual, continuously updated representation of a vehicle |
| Kuksa | Eclipse SDV component that provides the vehicle data model (VSS) server |
| Velocitas | Eclipse SDV framework used to build the vehicle applications |
| Ankaios | Eclipse SDV tool that manages the software running on each vehicle |
| Zenoh | Eclipse SDV communication middleware used for vehicle-to-cloud data transfer |
| FR | Functional Requirement |
| NFR | Non-Functional Requirement |

---

## 2. Overall Description

### 2.1 Product Perspective

The system is a new project built on existing Eclipse SDV open-source components (Kuksa, Velocitas, Ankaios, Zenoh). It has three layers:

- **Vehicle layer:** simulated vehicles, each running a digital twin and hazard-detection logic, managed by Ankaios.
- **Communication layer:** Zenoh carries data from the vehicles to the cloud.
- **Cloud layer:** ingestion, quality checks, storage, analytics, and a web dashboard.

A CI/CD pipeline builds, tests and deploys the system automatically.

### 2.2 Product Functions (Summary)

- Simulate a fleet of vehicles, each with a digital twin.
- Detect and report safety hazards in real time.
- Manage vehicle software remotely.
- Transmit vehicle data from vehicle to cloud.
- Ingest, quality-check, store and process fleet data in the cloud.
- Detect anomalies and calculate route efficiency.
- Present fleet status, hazards and performance in a web dashboard.
- Build, test and deploy the system automatically through CI/CD.

### 2.3 User Characteristics

- **Fleet operator:** the main user of the dashboard. Monitors vehicle status, hazard alerts and performance. Assumed to have ordinary computer/web skills, no specialized technical training.
- **Development team (Ahmad, Mohammad, Giancarlo):** builds, tests and maintains the system. Technical users with SDV, cloud and web-development knowledge.

### 2.4 Design and Implementation Constraints

- The four named Eclipse SDV projects must be used: Kuksa, Velocitas, Ankaios and Zenoh.
- No new tools may be introduced in Phase 2; every needed tool is chosen during Phase 1.
- Vehicle applications and cloud services are implemented in Python; the dashboard is implemented in JavaScript.
- Vehicle and fleet data is stored in PostgreSQL.
- Ankaios requires a Linux environment, so it runs on a shared Linux VM in the cloud.
- Velocitas only works with an older Kuksa version, so a compatible Kuksa version must be used.
- Source control and build automation use GitHub and GitHub Actions; services are containerized with Docker.

### 2.5 Assumptions and Dependencies

- Vehicles are simulated, not physical; sensor data is generated or replayed rather than read from real hardware.
- At least three simulated vehicles are available for testing and demonstration.
- The Eclipse SDV tools (Kuksa, Velocitas, Ankaios, Zenoh) stay compatible with each other for the project's duration.
- Phase 2 functionality depends on the Phase 1 core stack being complete and working.

---

## 3. Functional Requirements

Each requirement is tagged with the project phase it belongs to, as defined in the project charter.

### 3.1 Vehicle Simulation and Digital Twin

- **FR-1:** The system shall simulate a fleet of at least three software-defined vehicles. *[Phase 1]*
- **FR-2:** The system shall maintain a digital twin for each vehicle, based on the Kuksa Vehicle Signal Specification (VSS), extended with custom fleet and hazard signals. *[Phase 1]*
- **FR-3:** The system shall update each vehicle's digital twin with its speed, location, battery/fuel level and engine status. *[Phase 1]*

### 3.2 Hazard Detection

- **FR-4:** The system shall detect safety hazards on each vehicle, including harsh braking and traction loss. *[Phase 1]*
- **FR-5:** The system shall report detected hazard events to the cloud in real time. *[Phase 1]*

### 3.3 Vehicle Software Management

- **FR-6:** The system shall manage and update the software applications running on each simulated vehicle using Ankaios. *[Phase 1]*

### 3.4 Vehicle-to-Cloud Communication

- **FR-7:** The system shall transmit vehicle sensor data and hazard events from each vehicle to the cloud using Zenoh. *[Phase 1]*

### 3.5 Cloud Data Ingestion, Quality and Storage

- **FR-8:** The system shall ingest vehicle data received from the fleet in the cloud. *[Phase 1]*
- **FR-9:** The system shall store ingested vehicle data in a PostgreSQL database. *[Phase 1]*
- **FR-10:** The system shall check incoming data for quality issues, including missing, out-of-range and delayed values, before storing it. *[Phase 2]*

### 3.6 Data Processing and Analytics

- **FR-11:** The system shall analyze stored vehicle data to detect anomalies. *[Phase 2]*
- **FR-12:** The system shall calculate the efficiency/profitability of each completed route. *[Phase 2]*
- **FR-13:** The system may use a simple machine learning model to support anomaly detection or route-efficiency calculation. *[Phase 2 – optional]*

### 3.7 Web Dashboard

- **FR-14:** The system shall provide a web dashboard showing a live map of the vehicle fleet. *[Phase 1]*
- **FR-15:** The system shall display hazard alerts on the dashboard as they occur. *[Phase 1]*
- **FR-16:** The system shall display basic fleet performance information on the dashboard. *[Phase 1]*
- **FR-17:** The system shall extend the dashboard to show route performance and fleet history. *[Phase 2]*

### 3.8 CI/CD Pipeline

- **FR-18:** The system shall automatically build, test and deploy changes that are pushed to the main branch. *[Phase 1]*
- **FR-19:** The CI pipeline shall run automated tests against the integrated system before deployment. *[Phase 1]*

---

## 4. Non-Functional Requirements

- **NFR-1: Performance.** The system shall report a detected hazard event from the vehicle to the cloud within a few seconds, to support real-time alerting.
- **NFR-2: Reliability.** The system shall flag or reject incoming data that fails the quality checks rather than storing it silently.
- **NFR-3: Usability.** The dashboard shall present fleet status and alerts clearly enough that a fleet operator can understand them without specialized technical training.
- **NFR-4: Maintainability.** All system services shall be containerized with Docker, so that development, testing and deployment stay consistent.
- **NFR-5: Portability.** Components that require Linux (Ankaios) shall run on a dedicated Linux VM, so that team members on other operating systems are not blocked.
- **NFR-6: Availability.** The CI/CD pipeline shall keep the deployed system in a working state after each change merged to the main branch.
- **NFR-7: Scalability.** The architecture shall support at least three simulated vehicles and should not need to be redesigned to support more.

---

## 5. External Interface Requirements

### 5.1 User Interface

A web-based dashboard, accessible through a standard web browser, showing the live fleet map, hazard alerts, and fleet/route performance.

### 5.2 Software Interfaces

- Kuksa VSS server: vehicle digital twin data
- Velocitas: vehicle application framework
- Ankaios: vehicle software orchestration
- Zenoh: publish/subscribe communication between vehicle and cloud
- PostgreSQL: data storage
- GitHub Actions: CI/CD automation

### 5.3 Communication Interfaces

Vehicle-to-cloud communication uses Zenoh. Dashboard-to-backend communication uses standard web protocols (HTTP/WebSocket).

---

## 6. Out of Scope

- Real vehicles or vehicle hardware.
- Vehicle-to-vehicle communication.
- Mobile applications.
