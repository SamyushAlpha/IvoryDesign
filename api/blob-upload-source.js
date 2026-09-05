import { handleUpload } from '@vercel/blob/client';

export default async function handler(request, response) {
  if (request.method !== 'POST') return response.status(405).json({ error: 'Method not allowed' });
  const body = typeof request.body === 'string' ? JSON.parse(request.body) : request.body;
  if (body?.type === 'blob.generate-client-token') {
    const origin = `https://${process.env.VERCEL_PROJECT_PRODUCTION_URL || request.headers.host}`;
    const authorization = await fetch(`${origin}/admin/blob-upload-authorize/`, {
      headers: { cookie: request.headers.cookie || '' },
    });
    if (!authorization.ok) return response.status(403).json({ error: 'Staff login required' });
  }
  try {
    const result = await handleUpload({
      body,
      request,
      onBeforeGenerateToken: async (pathname) => {
        const safeName = pathname.split('/').pop().replace(/[^a-zA-Z0-9._-]/g, '-');
        if (!pathname.startsWith('team/portfolio/pdfs/') || !safeName.toLowerCase().endsWith('.pdf')) throw new Error('PDF files only');
        return {
          allowedContentTypes: ['application/pdf'],
          maximumSizeInBytes: 50 * 1024 * 1024,
          addRandomSuffix: true,
        };
      },
      onUploadCompleted: async () => {},
    });
    return response.status(200).json(result);
  } catch (error) {
    return response.status(400).json({ error: error?.message || 'PDF upload failed' });
  }
}
