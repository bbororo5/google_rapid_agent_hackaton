# Next.js frontend. Build context: REPO ROOT (it imports contract example JSON
# from ../../../../../../contracts, which lives outside apps/frontend).
FROM node:20-alpine

WORKDIR /app

# Install deps first (better caching).
COPY apps/frontend/package.json apps/frontend/
RUN cd apps/frontend && npm install

# Bring in the frontend source AND the contracts it imports at build time,
# preserving the relative layout the imports expect.
COPY apps/frontend apps/frontend
COPY contracts contracts

WORKDIR /app/apps/frontend
RUN npm run build

EXPOSE 3000
CMD ["npm", "run", "start"]
