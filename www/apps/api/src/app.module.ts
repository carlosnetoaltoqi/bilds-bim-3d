import { Module } from '@nestjs/common';
import { MongooseModule } from '@nestjs/mongoose';
import { HealthController } from './health/health.controller';

@Module({
  imports: [
    MongooseModule.forRoot(process.env.MONGODB_URI as string),
  ],
  controllers: [HealthController],
})
export class AppModule {}
