# ProductSense web — static SPA served by nginx on Cloud Run.
# The dist/ folder is built beforehand (vite build) with the prod VITE_* env,
# so this image just serves it. Listens on 8080 (Cloud Run default port).
FROM nginx:1.27-alpine
RUN rm -f /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY dist /usr/share/nginx/html
EXPOSE 8080
