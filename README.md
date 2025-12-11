# Create folder
RUN mkdir -p /var/task/awssdk

# Download AWS ESB Client SDK from Nexus
RUN curl -L -o /var/task/awssdk/aws-python-clientsdk-1.2.5.tar.gz \
    "https://nexusrepository.fanniemae.com/nexus/content/repositories/releases/com/fanniemae/emp/aws-python-clientsdk/1.2.5/aws-python-clientsdk-1.2.5.tar.gz"

# Optional: verify download
RUN ls -lrth /var/task/awssdk/

# Extract SDK
RUN tar -xzf /var/task/awssdk/aws-python-clientsdk-1.2.5.tar.gz -C /var/task/awssdk/

# Confirm extraction
RUN ls -lrth /var/task/awssdk/