const redis = require('redis');
const client = redis.createClient({
  url: process.env.REDIS_URL
});

client.on('error', (err) => {
    console.error('Redis error:', err);
});

export default async function handler(req, res) {
    const { index } = req.query;

    if (req.method === 'PUT') {
        const updatedSoftware = JSON.stringify(req.body);
        client.lset('softwareData', index, updatedSoftware, (err, reply) => {
            if (err) {
                return res.status(500).send(err);
            }
            res.send(reply);
        });
    } else if (req.method === 'DELETE') {
        client.lindex('softwareData', index, (err, data) => {
            if (err) {
                return res.status(500).send(err);
            }
            client.lrem('softwareData', 1, data, (err, reply) => {
                if (err) {
                    return res.status(500).send(err);
                }
                res.send(reply);
            });
        });
    } else {
        res.status(405).send('Method Not Allowed');
    }
}
