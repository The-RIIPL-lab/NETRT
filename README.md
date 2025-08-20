# NETRT - DICOM RT Structure Processor

NETRT is a service that listens for DICOM studies on a network port, automatically processes them to generate contour overlays from RT Structure Sets, and sends the newly created DICOM series to a specified destination.

It is designed to run continuously as a background service, making it ideal for automated research workflows. The recommended deployment method is using Docker.

## Key Features

- **DICOM Listener**: Receives DICOM studies over the network.
- **Automated Processing**: Extracts contour data from RTSTRUCT files, merges them into a single binary mask, and creates a new DICOM series with the mask as a graphical overlay.
- **Configurable**: All operational parameters (ports, AE titles, directories, processing options) are managed via a single `config.yaml` file.
- **Anonymization**: Built-in tools to anonymize DICOM data, with both "full" and "partial" modes available.
- **Logging**: Maintains detailed application and transaction logs for monitoring and debugging.
- **Deployment Ready**: Includes a `Dockerfile` and `docker-compose.yml` for easy and consistent deployment.

## Quick Start (Docker)

This is the recommended method for running NETRT.

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/)

### Steps

1.  **Clone the Repository**

    ```bash
    git clone <repository_url>
    cd NETRT
    ```

2.  **Configure the Application**

    Edit the `config.yaml` file to match your environment. You will need to set the correct IP addresses, ports, and AE titles for your DICOM listener and destination.

3.  **Create Data Directories**

    The `docker-compose.yml` file is configured to use a local `netrt_data` directory. Create it now:

    ```bash
    mkdir -p netrt_data/working netrt_data/logs
    ```

4.  **Build and Run the Container**

    Use Docker Compose to build the image and run the service in the background:

    ```bash
    docker-compose up --build -d
    ```

5.  **Verify the Service**

    Check the logs to ensure the service started correctly:

    ```bash
    docker-compose logs -f
    ```

    You should see messages indicating that the DICOM listener has started.

6.  **Stopping the Service**

    To stop the application, run:

    ```bash
    docker-compose down
    ```

## Further Information

For more detailed information on configuration, architecture, and advanced usage, please see the following documents:

-   **[DETAILS.md](DETAILS.md)**: In-depth explanation of the application's workflow, components, and a data flow diagram.
-   **[CONFIGURATION.md](CONFIGURATION.md)**: A complete reference for all options in the `config.yaml` file.
-   **[DEPLOYMENT.md](DEPLOYMENT.md)**: Instructions for alternative deployment methods, such as using systemd.