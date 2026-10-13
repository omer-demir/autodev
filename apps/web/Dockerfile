FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
COPY apps/web/package.json ./apps/web/package.json
RUN npm ci
COPY apps/web ./apps/web
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG WORKBENCH_API_URL=http://127.0.0.1:8000
ARG OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV WORKBENCH_API_URL=$WORKBENCH_API_URL
ENV OTEL_EXPORTER_OTLP_ENDPOINT=$OTEL_EXPORTER_OTLP_ENDPOINT
RUN npm --workspace apps/web run build

FROM node:22-alpine
WORKDIR /app
COPY --from=build /app ./
EXPOSE 3000
CMD ["npm", "--workspace", "apps/web", "run", "start"]