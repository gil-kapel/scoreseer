# ScoreSeer frontend — multi-stage: `dev` (next dev + inspector) and `prod`
# (Next standalone server). Compose selects the target.
FROM node:22-slim AS deps
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json* ./
RUN npm install

# --- dev: next dev server, source bind-mounted by compose ---
FROM node:22-slim AS dev
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . ./
EXPOSE 3000 9229
CMD ["npm", "run", "dev"]

# --- build: compile the standalone production bundle ---
FROM node:22-slim AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . ./
RUN npm run build

# --- prod: run the compiled app with `next start` (no standalone) ---
FROM node:22-slim AS prod
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/next.config.ts ./next.config.ts
EXPOSE 3000
CMD ["npm", "run", "start"]
