/**
 * Entry point for redirection recording lambda function.  The function
 * takes the following arguments.
 *
 * Required:
 * - url {string}: The url to begin crawling from
 *
 * Optional:
 * - bucket {string}: The S3 bucket to record results to.  If not provided,
 *                    then the results will not be written to S3.
 * - seconds {int}:   The maximum number of seconds to follow redirects for,
 *                    before ending crawling and recording the results to S3.
 *                    If provided, must be > 0 and less <= 300.
 *                    (Defaults to 240).
 * - debug (boolean): Whether to run in debug mode. If true, uses local chrome,
 *                    prints logging information to STDOUT, etc. (Defaults to
 *                    false).
 */

const path = require('path')

const utilsLib = require('./lib/utils')
const crawlLib = require('./lib/crawl')
const s3Lib = require('./lib/s3')
const lambdaLib = require('./lib/lambda')

const localResourcesDir = path.join(__dirname, 'resources')
const chromeHeadlessPath = path.join(localResourcesDir, 'headless-chromium')

const handler = (args, _, callback) => {
  if (process.env.S3_BUCKET !== undefined) {
    args.bucket = process.env.S3_BUCKET
  }

  if (args.Records !== undefined) {
    if (args.Records.length > 0) {
      if (args.Records[0].body !== undefined) {
        args.url = args.Records[0].body
      }
    }
  }

  const validationResult = utilsLib.validateArgs(args)
  if (validationResult !== undefined) {
    throw validationResult.msg
  }

  const crawlArgs = {
    url: args.url,
    profile: args.profile,
    seconds: (args.seconds || 240),
    debug: true
  }

  const logger = crawlArgs.debug === true ? console.dir : _ => { }

  if (args.chromePath !== undefined) {
    crawlArgs.chromePath = args.chromePath
  } else {
    crawlArgs.chromePath = chromeHeadlessPath
  }

  logger('Beginning crawl with following settings:')
  logger(crawlArgs)

  const onCrawlComplete = crawlResults => {
    if (!args.bucket) {
      logger('no s3 bucket provided; not sending to S3 or lambda.')
      callback(crawlResults)
      return
    }

    let s3KeyHandle
    s3Lib.record(crawlArgs.url, args.bucket, crawlResults, crawlArgs.debug)
      .then(s3Key => {
        s3KeyHandle = s3Key
        return lambdaLib.trigger(s3Key, crawlArgs.debug)
      })
      .then(_ => {
        logger(`Launched lambda function for ${args.bucket}:${s3KeyHandle}.`)
        callback(null, crawlResults)
      })
  }

  crawlLib.crawl(crawlArgs, onCrawlComplete).catch()
}

module.exports.handler = handler
