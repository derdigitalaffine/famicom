FROM node:22-alpine AS builder
WORKDIR /web
COPY package.json ./
RUN npm install --no-audit --no-fund
COPY . .
RUN npm run build
FROM caddy:2.10.2-alpine
COPY --from=builder /web/dist /srv
COPY --from=builder /web/node_modules/converse.js/dist /srv/converse
