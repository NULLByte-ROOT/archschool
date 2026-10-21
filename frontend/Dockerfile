FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ARG VITE_API_URL=/api
ENV VITE_API_URL=${VITE_API_URL}

RUN npm run build

FROM nginx:1.27-alpine

# The stock default.conf would collide with the template rendered below.
RUN rm -f /etc/nginx/conf.d/default.conf

# Rendered by /docker-entrypoint.d/20-envsubst-on-templates.sh at startup.
# Restricting substitution to BACKEND_* keeps nginx variables ($host, $uri,
# $scheme, ...) intact.
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
ENV NGINX_ENVSUBST_FILTER=^BACKEND_

COPY --from=build /app/dist /usr/share/nginx/html

# Build revision, comparable with the backend's GET /api/health revision.
ARG GIT_SHA=unknown
RUN printf '%s\n' "${GIT_SHA}" > /usr/share/nginx/html/version

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
