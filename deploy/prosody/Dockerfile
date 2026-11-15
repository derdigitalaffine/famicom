ARG PROSODY_IMAGE=prosodyim/prosody:13.0
FROM ${PROSODY_IMAGE}
USER root
# Community Prosody auth module: XMPP credentials are checked against FamiCom's single identity source.
RUN prosodyctl install --server=https://modules.prosody.im/rocks/ mod_auth_http
