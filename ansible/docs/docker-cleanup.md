# Docker-Cleanup in Semaphore

Das Playbook `ansible/playbooks/cleanup-docker.yaml` verwendet denselben Host
wie `deploy-docker-apps.yaml`: `docker01`.

Es entfernt nicht von Containern referenzierte Images (auch mit Tags) und
ungenutzten Build-Cache mit dem Filter `until: 168h` (7 Tage).
Bei Images bezieht sich dieser Filter auf das Erstellungsdatum des Images,
nicht auf den Zeitpunkt des Downloads oder der letzten Verwendung.
Entfernte Images müssen bei späterem Bedarf erneut heruntergeladen werden.
Gestoppte und laufende Container, Volumes, Netzwerke und App-Verzeichnisse
bleiben erhalten. Von gestoppten Containern referenzierte Images bleiben daher
ebenfalls erhalten.

## Task-Template

- Name: `Docker Cleanup`
- Typ: Ansible
- Repository und Branch: wie beim App-Deployment
- Playbook: `ansible/playbooks/cleanup-docker.yaml`
- Inventory: `ansible/inventory/hosts`, mit demselben SSH-Key wie beim Deployment
- Variable Group: mit `ANSIBLE_CONFIG=ansible/ansible.cfg` und den bisherigen
  Rollen-/Collection-Pfaden; App-Secrets werden nicht benötigt

Optional in den Ansible Extra Variables die Frist überschreiben:

```json
{"docker_cleanup_age": "336h"}
```

Zunächst manuell starten. Bei gewünschter regelmäßiger Ausführung einen
wöchentlichen Zeitplan im Semaphore-Template anlegen, außerhalb der
Deployment- und Build-Zeiten. Ein Check-Mode-Lauf liefert bei diesem Modul
keine verlässliche Vorschau der zu löschenden Objekte.

Lokal aus dem Verzeichnis `ansible`:

```sh
ansible-playbook playbooks/cleanup-docker.yaml
```

Moduldokumentation:
https://docs.ansible.com/projects/ansible/latest/collections/community/docker/docker_prune_module.html
