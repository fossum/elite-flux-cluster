FROM python:3.13-slim-bookworm

# Arguments for non-root user
ARG USERNAME=dev
ARG UID=25000
ARG GID=25000

ENV DEBIAN_FRONTEND=noninteractive \
	LANG=C.UTF-8 \
	LC_ALL=C.UTF-8

# Install base packages, OpenSSH server, pipenv, docker CLI
RUN apt-get update && \
	apt-get install -y --no-install-recommends \
	ca-certificates curl gnupg lsb-release locales tzdata \
	openssh-server \
	# we'll install pipenv via pip to get latest
	uidmap git vim less iproute2 iputils-ping \
	docker.io && \
	rm -rf /var/lib/apt/lists/*

# Latest pip & pipenv
RUN python -m pip install --no-cache-dir --upgrade pip pipenv

# Configure SSHD
RUN mkdir -p /var/run/sshd /etc/ssh && \
	sed -ri 's/^#?PasswordAuthentication .*/PasswordAuthentication yes/' /etc/ssh/sshd_config && \
	sed -ri 's/^#?PermitRootLogin .*/PermitRootLogin no/' /etc/ssh/sshd_config && \
	echo 'PubkeyAuthentication yes' >> /etc/ssh/sshd_config && \
	echo 'X11Forwarding no' >> /etc/ssh/sshd_config && \
	echo 'ClientAliveInterval 120' >> /etc/ssh/sshd_config && \
	echo 'ClientAliveCountMax 2' >> /etc/ssh/sshd_config

# Create non-root user and home
RUN groupadd -g ${GID} ${USERNAME} && \
	useradd -m -s /bin/bash -u ${UID} -g ${GID} ${USERNAME}

# Add user to docker group (note: group id may not match socket; set via Pod securityContext fsGroup if needed)
RUN groupadd -f -g 999 docker && usermod -aG docker ${USERNAME}

# Prepare SSH for the user
RUN mkdir -p /home/${USERNAME}/.ssh && \
	chown -R ${USERNAME}:${USERNAME} /home/${USERNAME}/.ssh && \
	chmod 700 /home/${USERNAME}/.ssh

# Python 3.13 is provided by the base image (python:3.13)

# Expose SSH port
EXPOSE 22

# Generate SSH host keys at build-time (ensures non-root sessions work at runtime)
RUN ssh-keygen -A

# Copy start script
COPY start_server /usr/bin/start_server
RUN chmod +x /usr/bin/start_server

# Workdir
WORKDIR /home/${USERNAME}

# Entry point (via Helm chart command)
CMD ["/usr/bin/start_server"]
