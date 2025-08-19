# K3S Install

## Worker Nodes

1. Install prerequisites.

```bash
sudo apt install nfs-common
```

1. Get the existing token from a server node.

```bash
~ » sudo cat /var/lib/rancher/k3s/server/node-token
[sudo] password for username:
<<<REALLY LONG HASH>>>::server:<<<SMALLER HASH>>>
```

1. Fill in the variables below and execute on the new worker node.

```bash
~ » curl -sfL https://get.k3s.io | K3S_URL=https://<master node IP>:6443 K3S_TOKEN=<<<REALLY LONG HASH>>>::server:<<<SMALLER HASH>>> sh -
```