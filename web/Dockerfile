FROM --platform=$BUILDPLATFORM node:22-alpine AS build
RUN corepack enable
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm build

FROM nginx:alpine
ENV SKILLHUB_TRUST_FORWARDED_PROTO=false
COPY --from=build /app/dist /usr/share/nginx/html
RUN sed 's|<base href="/" />|<base href="${SKILLHUB_WEB_BASE_HREF}" />|' \
    /usr/share/nginx/html/index.html \
    > /usr/share/nginx/html/index.html.template \
    && rm /usr/share/nginx/html/index.html
COPY --from=build /app/src/docs/skill.md.template /usr/share/nginx/html/registry/skill.md.template
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY runtime-config.js.template /usr/share/nginx/html/runtime-config.js.template
COPY docker-entrypoint.d/20-base-path-routing.sh /docker-entrypoint.d/20-base-path-routing.sh
RUN sed -i 's/\r$//' /docker-entrypoint.d/20-base-path-routing.sh
RUN chmod +x /docker-entrypoint.d/20-base-path-routing.sh
COPY docker-entrypoint.d/30-runtime-config.sh /docker-entrypoint.d/30-runtime-config.sh
RUN sed -i 's/\r$//' /docker-entrypoint.d/30-runtime-config.sh
RUN chmod +x /docker-entrypoint.d/30-runtime-config.sh
EXPOSE 80
HEALTHCHECK --interval=10s --timeout=3s \
  CMD wget -qO- http://127.0.0.1/nginx-health || exit 1
