# NoteGen 前端镜像（多阶段：deps → build → run）。
# NEXT_PUBLIC_API_URL 是浏览器端常量，构建期烧死——局域网他机访问时
# 用 build arg 指到宿主机 IP：NEXT_PUBLIC_API_URL=http://192.168.x.x:8000
# public/notes、public/videos 不进镜像（见 .dockerignore），运行时 volume 挂入。
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:20-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

FROM node:20-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app ./
EXPOSE 3000
CMD ["npm", "run", "start"]
