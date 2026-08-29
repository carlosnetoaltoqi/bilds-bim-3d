import { Controller, Get, InternalServerErrorException } from '@nestjs/common';
import { MongoClient } from 'mongodb';

@Controller()
export class HealthController {
  @Get('health')
  async health() {
    const uri = process.env.MONGODB_URI;
    if (!uri) throw new InternalServerErrorException('MONGODB_URI não configurado');

    const client = new MongoClient(uri, { serverSelectionTimeoutMS: 5000 });
    try {
      await client.connect();
      const { version } = await client.db().admin().command({ buildInfo: 1 });
      return { status: 'ok', mongo: version };
    } finally {
      await client.close();
    }
  }
}
