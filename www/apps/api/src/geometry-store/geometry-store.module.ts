import { Module } from '@nestjs/common';
import { DiskGeometryStore } from './disk-geometry-store';

@Module({
  providers: [{ provide: 'GEOMETRY_STORE', useClass: DiskGeometryStore }],
  exports: ['GEOMETRY_STORE'],
})
export class GeometryStoreModule {}
