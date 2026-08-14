# Two targets. `dev` runs the Vite dev server with hot reload and proxies
# `/api` to the backend container. `runtime` serves the built bundle.
#
# The deployed shape MAY skip `runtime` entirely: a static bundle in S3 behind
# the existing CloudFront distribution costs less than a container that serves
# it. Build with `--target runtime` only when the site runs a web server.

FROM node:22-slim AS deps
WORKDIR /app
# Copy the manifests alone, so a source change does not reinstall packages.
COPY package.json package-lock.json ./
RUN npm ci

FROM deps AS dev
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev"]

FROM deps AS build
COPY . .
RUN npm run build

FROM nginx:alpine AS runtime
COPY --from=build /app/dist /usr/share/nginx/html
# The React app is one page. Serve `index.html` for any path the bundle owns.
RUN printf 'server {\n\
  listen 80;\n\
  root /usr/share/nginx/html;\n\
  location / { try_files $uri $uri/ /index.html; }\n\
}\n' > /etc/nginx/conf.d/default.conf
EXPOSE 80
