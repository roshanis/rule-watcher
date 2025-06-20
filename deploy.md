# Deploying CMS Rule Watcher to Vercel

## Prerequisites

1. **Vercel Account**: Sign up at [vercel.com](https://vercel.com)
2. **Vercel CLI**: Install globally
   ```bash
   npm install -g vercel
   ```

## Deployment Steps

### Option 1: Deploy via Vercel CLI

1. **Login to Vercel**:
   ```bash
   vercel login
   ```

2. **Deploy from project directory**:
   ```bash
   vercel
   ```
   
3. **Follow the prompts**:
   - Set up and deploy? `Y`
   - Which scope? Choose your account
   - Link to existing project? `N` (for first deployment)
   - What's your project's name? `cms-rule-watcher`
   - In which directory is your code located? `./`

4. **Set Environment Variables** (if needed):
   ```bash
   vercel env add OPENAI_API_KEY
   ```

### Option 2: Deploy via GitHub Integration

1. **Push to GitHub** (if not already done):
   ```bash
   git add .
   git commit -m "Add Vercel deployment configuration"
   git push origin main
   ```

2. **Import Project on Vercel**:
   - Go to [vercel.com/dashboard](https://vercel.com/dashboard)
   - Click "New Project"
   - Import your GitHub repository
   - Configure project settings:
     - Framework Preset: `Other`
     - Root Directory: `./`
     - Build Command: (leave empty)
     - Output Directory: (leave empty)

3. **Deploy**: Click "Deploy"

## Configuration Files

The following files have been created for Vercel deployment:

- **`vercel.json`**: Vercel configuration
- **`api/index.py`**: Serverless function entry point
- **`requirements.txt`**: Python dependencies

## Important Notes

### Limitations in Serverless Environment

1. **No Persistent Storage**: 
   - Votes and comments reset on cold starts
   - Document state tracking doesn't persist between deployments
   - For production, integrate with a database (PostgreSQL, Redis, etc.)

2. **Function Timeout**: 
   - Maximum execution time is 30 seconds
   - API calls are optimized for this constraint

3. **Memory Limitations**:
   - Limited memory per function execution
   - Large document processing may need optimization

### Recommended Production Enhancements

1. **Database Integration**:
   ```bash
   # Add to requirements.txt
   psycopg2-binary  # for PostgreSQL
   redis           # for Redis
   ```

2. **Environment Variables**:
   - `DATABASE_URL`: PostgreSQL connection string
   - `REDIS_URL`: Redis connection string
   - `OPENAI_API_KEY`: If using OpenAI features

3. **Caching Strategy**:
   - Implement API response caching
   - Use CDN for static assets

## Testing Deployment

After deployment, test these endpoints:

- `https://your-app.vercel.app/` - Main interface
- `https://your-app.vercel.app/api/documents` - API endpoint
- `https://your-app.vercel.app/search?q=medicare` - Search functionality

## Troubleshooting

### Common Issues

1. **Build Failures**:
   - Check Python version compatibility
   - Verify all dependencies in requirements.txt

2. **Function Timeouts**:
   - Reduce API request timeout values
   - Implement pagination for large result sets

3. **Import Errors**:
   - Ensure all Python files are in the correct structure
   - Check sys.path modifications in api/index.py

### Logs and Debugging

View deployment logs:
```bash
vercel logs
```

View function logs:
```bash
vercel logs --follow
```

## Custom Domain (Optional)

1. **Add Domain in Vercel Dashboard**:
   - Go to Project Settings > Domains
   - Add your custom domain

2. **Configure DNS**:
   - Add CNAME record pointing to `cname.vercel-dns.com`
   - Or use Vercel nameservers

## Security Considerations

1. **Rate Limiting**: Configured but may need database backend for persistence
2. **CORS**: Configured for web interface
3. **Input Validation**: Implemented for all user inputs
4. **HTTPS**: Automatically provided by Vercel

## Monitoring

Consider adding:
- **Vercel Analytics**: Built-in performance monitoring
- **Error Tracking**: Sentry integration
- **Uptime Monitoring**: External service for API availability 