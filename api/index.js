const redis = require('redis');
const client = redis.createClient({
  url: process.env.REDIS_URL // Stellen Sie sicher, dass Ihre REDIS_URL Umgebungsvariable in Vercel eingerichtet ist
});

client.on('error', (err) => {
    console.error('Redis error:', err);
});

export default async function handler(req, res) {
    if (req.method === 'GET') {
        client.lrange('softwareData', 0, -1, (err, data) => {
            if (err) {
                return res.status(500).send(err);
            }
            const softwareData = data.map(item => JSON.parse(item));
            res.send(softwareData);
        });
    } else if (req.method === 'POST') {
        const newSoftware = JSON.stringify(req.body);
        client.rpush('softwareData', newSoftware, (err, reply) => {
            if (err) {
                return res.status(500).send(err);
            }
            res.status(201).send(reply);
        });
    } else {
        res.status(405).send('Method Not Allowed');
    }
}
