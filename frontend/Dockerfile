# ============================================================
# NewsLens frontend - React + Vite + TypeScript
# Stage 1 builds static assets, Stage 2 serves them with nginx.
# nginx also reverse-proxies /api to the backend container (see nginx.conf),
# so in this deployment the frontend needs no VITE_API_BASE_URL.
# ============================================================

# ---- Build stage ----
FROM node:20-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# `npm run build` runs `tsc --noEmit && vite build` (type-check + bundle).
RUN npm run build

# ---- Runtime stage ----
FROM nginx:1.27-alpine AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
