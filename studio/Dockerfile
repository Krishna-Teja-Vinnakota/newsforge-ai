FROM node:24-alpine

WORKDIR /app
COPY studio/package.json ./
RUN npm install
COPY studio/ ./

EXPOSE 5174
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5174"]
