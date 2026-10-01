# syntax=docker/dockerfile:1.7
# ---------------------------------------------------------------- build stage
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund
COPY . .
RUN npm run build

# ---------------------------------------------------------------- runtime stage
FROM nginx:1.27-alpine
LABEL org.opencontainers.image.title="netmon-frontend" \
      org.opencontainers.image.description="NetMon web dashboard" \
      org.opencontainers.image.licenses="MIT"
# The nginx image renders /etc/nginx/templates/*.template with envsubst at start-up.
ENV NETMON_API_UPSTREAM=backend:8000
COPY docker/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://127.0.0.1/healthz || exit 1
