# Varagrill frontend

## Nginx para servir el frontend

1. Compila React:

```bash
cd /home/mariadb/app/frontend
npm install
npm run build
```

2. Copia el archivo de Nginx:

```bash
sudo cp /home/mariadb/app/deploy/nginx.varagrilladmin.conf.example /etc/nginx/sites-available/varagrilladmin.com
```

3. Activa el sitio:

```bash
sudo ln -s /etc/nginx/sites-available/varagrilladmin.com /etc/nginx/sites-enabled/varagrilladmin.com
```

4. Verifica y recarga Nginx:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

Si `/` responde pero `/api/` da `404`, revisa que Nginx esté cargando ese archivo y no el sitio por defecto:

```bash
sudo nginx -T | grep -n "varagrilladmin.com\|location /api/\|location /admin/"
```

Si no aparece tu bloque, reactiva el sitio y recarga Nginx:

```bash
sudo ln -sf /etc/nginx/sites-available/varagrilladmin.com /etc/nginx/sites-enabled/varagrilladmin.com
sudo nginx -t
sudo systemctl reload nginx
```

## Archivo de Nginx

El archivo que debes poner en `/etc/nginx/sites-available/varagrilladmin.com` es este:

```nginx
server {
    listen 80;
    server_name varagrilladmin.com www.varagrilladmin.com;

    client_max_body_size 20m;

    root /var/www/varagrilladmin/dist;
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /admin/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /var/www/varagrilladmin/staticfiles/;
        access_log off;
        expires 30d;
    }

    location /assets/ {
        alias /var/www/varagrilladmin/dist/assets/;
        access_log off;
        expires 30d;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

## Importante

- Nginx sirve el frontend compilado desde `/home/mariadb/app/frontend/dist`.
- Django debe estar corriendo en `127.0.0.1:8000`.
- Si usas Cloudflare Tunnel, el service debe apuntar a `http://127.0.0.1:80`.
