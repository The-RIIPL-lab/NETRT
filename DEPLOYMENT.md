# NETRT Deployment Guide

This guide provides instructions for deploying the NETRT application using Docker and systemd.

## Prerequisites

-   Docker installed (for Docker deployment).
-   Python 3.8+ installed (for systemd deployment without Docker, though Docker is recommended for consistency).
-   Access to a terminal or command line.

## 1. Configuration

Before deploying, ensure you have a `config.yaml` file prepared. Refer to the `CONFIGURATION.md` guide for details on all available options. You will need to make this configuration file accessible to the application, either by placing it in the expected location or by mounting it into the Docker container.

Key configuration items to review for deployment:

-   `dicom_listener`: `host`, `port`, `ae_title`.
-   `dicom_destination`: `ip`, `port`, `ae_title`.
-   `directories`: `working`, `logs`. These will typically be mounted as volumes in Docker.
-   `logging`: Ensure log levels and paths are appropriate for your environment.

## 2. Docker Deployment

Docker is the recommended method for deploying NETRT as it encapsulates all dependencies and provides a consistent environment.

### Building the Docker Image

1.  Navigate to the root directory of the NETRT application (where the `Dockerfile` is located).
2.  Build the Docker image using the following command:

    ```bash
    docker build -t netrt-app .
    ```
    This will create an image named `netrt-app`.

### Running the Docker Container

When running the container, you need to:

-   Expose the DICOM listener port.
-   Mount volumes for persistent data (working directory, logs) and configuration.

Example `docker run` command:

```bash
docker run -d \
    --name netrt-instance \
    -p 11112:11112/tcp \
    -v /path/on/host/to/your/config.yaml:/app/config/config.yaml:ro \
    -v /path/on/host/to/netrt_working_data:/home/appuser/CNCT_working \
    -v /path/on/host/to/netrt_logs:/home/appuser/CNCT_logs \
    --restart unless-stopped \
    netrt-app
```

**Explanation:**

-   `-d`: Run the container in detached mode (in the background).
-   `--name netrt-instance`: Assign a name to the container for easier management.
-   `-p 11112:11112/tcp`: Map port 11112 on the host to port 11112 in the container (adjust if your `config.yaml` uses a different listener port).
-   `-v /path/on/host/to/your/config.yaml:/app/config/config.yaml:ro`: Mount your custom `config.yaml` into the container. The `:ro` flag makes it read-only within the container, which is good practice for configuration files.
    *   **Important**: The application inside the Docker container expects the config file at `/app/config/config.yaml` as specified in the `CMD` instruction of the Dockerfile.
-   `-v /path/on/host/to/netrt_working_data:/home/appuser/CNCT_working`: Mount a host directory to `/home/appuser/CNCT_working` inside the container. This is where studies will be processed and quarantined. Ensure this path matches the `directories.working` path (after home expansion) in your `config.yaml` if you want the container to use this mounted volume correctly.
-   `-v /path/on/host/to/netrt_logs:/home/appuser/CNCT_logs`: Mount a host directory to `/home/appuser/CNCT_logs` for persistent log storage. Ensure this path matches `directories.logs` in your `config.yaml`.
-   `--restart unless-stopped`: Configure the container to restart automatically unless explicitly stopped.
-   `netrt-app`: The name of the Docker image to use.

**Note on Paths in `config.yaml` for Docker:**
When using Docker, the paths specified in `config.yaml` for `directories.working` and `directories.logs` should correspond to the paths *inside the container* (e.g., `/home/appuser/CNCT_working`, `/home/appuser/CNCT_logs` as per the Dockerfile defaults and volume mounts). The Docker volume mounts handle mapping these container paths to your host system paths.

### Viewing Logs

You can view the container logs using:

```bash
docker logs netrt-instance
```

Or, if you have mounted the logs directory, you can access the log files directly on your host system at `/path/on/host/to/netrt_logs`.

## 3. Systemd Service Deployment (Linux)

If you prefer to run the application directly on a Linux host without Docker (not generally recommended for production due to dependency management), you can use the provided systemd service unit file.

### Prerequisites for Systemd:

-   The NETRT application code cloned or copied to a directory on the host (e.g., `/opt/netrt`).
-   All Python dependencies listed in `requirements.txt` installed in the Python environment that systemd will use.
-   A dedicated user for running the application (e.g., `appuser`, matching the Dockerfile setup for consistency, though you can choose another). This user needs write permissions to the configured working and log directories.

### Setup Steps:

1.  **Place Application Code**: Ensure the NETRT application code is on your server, for example, in `/opt/netrt`.

2.  **Install Dependencies**:
    ```bash
    pip install -r /opt/netrt/requirements.txt
    ```

3.  **Create User (if not existing)**:
    ```bash
    sudo groupadd appgroup
    sudo useradd --system --no-create-home -g appgroup appuser
    ```

4.  **Prepare Configuration File**: Place your `config.yaml` in a suitable location, e.g., `/etc/netrt/config.yaml` or `/opt/netrt/config.yaml`.

5.  **Create Log and Working Directories**: Ensure the directories specified in your `config.yaml` for `logs` and `working` exist and are writable by the `appuser`.
    ```bash
    sudo mkdir -p /var/log/netrt /var/lib/netrt/working
    sudo chown -R appuser:appgroup /var/log/netrt /var/lib/netrt/working
    # Adjust your config.yaml to point to these paths, e.g.:
    # directories:
    #   working: "/var/lib/netrt/working"
    #   logs: "/var/log/netrt"
    ```

6.  **Copy Systemd Unit File**: Copy the example unit file `netrt.service.example` to `/etc/systemd/system/netrt.service`.
    ```bash
    sudo cp /opt/netrt/netrt.service.example /etc/systemd/system/netrt.service
    ```

7.  **Edit the Unit File (`/etc/systemd/system/netrt.service`)**:
    Adjust the following lines as needed:
    -   `User=appuser` and `Group=appgroup`: Change if you used a different user/group.
    -   `WorkingDirectory=/opt/netrt`: Change if you placed the application code elsewhere.
    -   `ExecStart=/usr/bin/python3 /opt/netrt/main.py --config /etc/netrt/config.yaml`: 
        -   Ensure the path to `python3` is correct for your system.
        -   Adjust the path to `main.py` if your `WorkingDirectory` is different.
        -   Update the path to your `config.yaml` file.

8.  **Reload Systemd Daemon**:
    ```bash
    sudo systemctl daemon-reload
    ```

9.  **Enable and Start the Service**:
    -   To enable the service to start on boot:
        ```bash
        sudo systemctl enable netrt.service
        ```
    -   To start the service immediately:
        ```bash
        sudo systemctl start netrt.service
        ```

10. **Check Service Status**:
    ```bash
    sudo systemctl status netrt.service
    ```
    You can view logs using `journalctl`:
    ```bash
    sudo journalctl -u netrt.service -f
    ```

## Updating the Application

### Docker

1.  Pull the latest code changes (if you built the image from a Git repository).
2.  Rebuild the Docker image: `docker build -t netrt-app .`
3.  Stop and remove the old container: `docker stop netrt-instance && docker rm netrt-instance`
4.  Run a new container using the updated image with the same `docker run` command as before.

### Systemd

1.  Stop the service: `sudo systemctl stop netrt.service`
2.  Update the application code in its directory (e.g., `/opt/netrt`) by pulling changes or copying new files.
3.  Update dependencies if `requirements.txt` has changed: `pip install -r /opt/netrt/requirements.txt`
4.  Restart the service: `sudo systemctl start netrt.service`

This guide provides a starting point for deploying NETRT. Always adapt the instructions and configurations to your specific environment and security requirements.

