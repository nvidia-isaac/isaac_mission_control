FROM nvcr.io/nvidia/base/ubuntu:22.04_20240212
ARG DEBIAN_FRONTEND=noninteractive

# Install python
RUN apt update && \
    apt install -y ca-certificates curl software-properties-common && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt install -y bash python3.10 python3.10-dev python3.10-distutils

# Create symlinks
RUN if [ -L /usr/bin/python3 ]; then unlink /usr/bin/python3; fi && \
    ln -s /usr/bin/python3.10 /usr/bin/python3 && \
    ln -s /usr/bin/python3 /usr/bin/python

# Install pip using apt and upgrade
RUN apt install -y python3.10-venv python3-pip && \
    python3 -m pip install --upgrade pip

# Verify the installation
RUN python3 --version

WORKDIR /app

# Copy requirements first for better caching
COPY waypoint_selection_ui/requirements.txt .
RUN pip install -r requirements.txt

# Copy the waypoint_selection_ui code
COPY waypoint_selection_ui/ ./waypoint_selection_ui/

# Create upload directories
RUN mkdir -p uploads/maps uploads/configs

# Expose the service port
EXPOSE 8051

# Run the application
CMD ["python", "-m", "waypoint_selection_ui.main"] 