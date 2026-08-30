import {
  Controller,
  Post,
  Body,
  Get,
  UnauthorizedException,
  UseGuards,
  Req,
} from '@nestjs/common';
import * as jwt from 'jsonwebtoken';
import { AuthGuard } from './auth.guard';
import { Request } from 'express';

@Controller('auth')
export class AuthController {
  @Post('login')
  login(@Body() body: { email: string; password: string }) {
    const { email, password } = body ?? {};
    const seedUser = process.env.SEED_USER;
    const seedPassword = process.env.SEED_PASSWORD;
    const jwtSecret = process.env.JWT_SECRET;

    if (!seedUser || !seedPassword || !jwtSecret) {
      throw new Error('SEED_USER, SEED_PASSWORD and JWT_SECRET must be set');
    }

    if (email !== seedUser || password !== seedPassword) {
      throw new UnauthorizedException('Credenciais inválidas');
    }

    const token = jwt.sign(
      { sub: seedUser, email: seedUser },
      jwtSecret,
      { expiresIn: '7d' },
    );
    return { token };
  }

  @UseGuards(AuthGuard)
  @Get('me')
  me(@Req() req: Request) {
    return { email: (req as any).user.email };
  }
}
