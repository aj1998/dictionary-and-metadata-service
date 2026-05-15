import { NextRequest, NextResponse } from 'next/server';
import { MongoClient } from 'mongodb';

const MONGODB_URI = process.env.MONGODB_URI ?? 'mongodb://localhost:27017';
const MONGODB_DB  = process.env.MONGODB_DB  ?? 'jain_kb';

export async function POST(req: NextRequest): Promise<NextResponse> {
  const body = await req.json();
  const { name, email, type, message, route } = body;
  // basic server-side validation
  if (!type || !message || message.length < 10) {
    return NextResponse.json({ error: 'invalid_input' }, { status: 400 });
  }
  try {
    const client = new MongoClient(MONGODB_URI);
    await client.connect();
    const db = client.db(MONGODB_DB);
    await db.collection('feedback').insertOne({
      name: name ?? null,
      email: email ?? null,
      type,
      message,
      route: route ?? null,
      created_at: new Date(),
    });
    await client.close();
    return NextResponse.json({ ok: true });
  } catch (err) {
    console.error('feedback insert failed', err);
    return NextResponse.json({ error: 'server_error' }, { status: 500 });
  }
}
