import unittest, random, sys, time
sys.path.extend(['.','..','py'])
import h2o, h2o_browse as h2b, h2o_exec as h2e, h2o_hosts, h2o_import as h2i, h2o_cmd, h2o_util

# new ...ability to reference cols
# src[ src$age<17 && src$zip=95120 && ... , ]
# can specify values for enums ..values are 0 thru n-1 for n enums

exprList = [
    'h=c(1); h = xorsum(r1[,1])',
]

ROWS = 10000

#********************************************************************************
def write_syn_dataset(csvPathname, rowCount, colCount, expectedMin, expectedMax, SEEDPERFILE, sel):
    dsf = open(csvPathname, 'w')
    expectedRange = (expectedMax - expectedMin)
    expectedFpSum = float(0)
    expectedUllSum = int(0)
    for row in range(rowCount):
        rowData = []
        for j in range(colCount):
            value = expectedMin + (random.random() * expectedRange)
            if 1==1:
                # value = row * 2

                # bad sum
                # value = 5555555555555 + row
                # bad
                # value = 555555555555 + row
                # value = 55555555555 + row

                # fail
                # value = 5555555555 + row
                # exp = random.randint(0,120)
                # 50 bad?

                # constrain the dynamic range of the numbers to be within IEEE-754 support
                # without loss of precision when adding. Why do we care though?
                # could h2o compress if values are outside that kind of dynamic range ?
                exp = random.randint(0,40)
                value = 3 + (2 ** exp) 

                # value = -1 * value
                # value = 2e9 + row
                # value = 3 * row
            r = random.randint(0,1)
            if False and r==0:
                value = -1 * value
            # hack

            # print "%30s" % "expectedUllSum (0.16x):", "0x%0.16x" % expectedUllSum

            # Now that you know how many decimals you want, 
            # say, 15, just use a rstrip("0") to get rid of the unnecessary 0s:
            # fix. can't rstrip if .16e is used because trailing +00 becomes +, causes NA
            if 1==0:
                # get the expected patterns from python
                fpResult = float(value)
                expectedUllSum ^= h2o_util.doubleToUnsignedLongLong(fpResult)
                expectedFpSum += fpResult
                s = ("%.16f" % value).rstrip("0")
                # since we're printing full fp precision always here, we shouldn't have 
                # to suck the formatted fp string (shorter?) back in
            # use a random fp format (string). use sel to force one you like
            else:
                NUM_CASES = h2o_util.fp_format()
                # s = h2o_util.fp_format(value, sel=None) # random
                s = h2o_util.fp_format(value, sel=sel) # use same case for all numbers
                # now our string formatting will lead to different values when we parse and use it 
                # so we move the expected value generation down here..i.e after we've formatted the string
                # we'll suck it back in as a fp number
                # get the expected patterns from python
                fpResult = float(s)
                expectedUllSum ^= h2o_util.doubleToUnsignedLongLong(fpResult)
                expectedFpSum += fpResult
            # s = ("%.16e" % value)
            rowData.append(s)

        rowDataCsv = ",".join(map(str,rowData))
        dsf.write(rowDataCsv + "\n")

    dsf.close()
    # zero the upper 4 bits of xorsum like h2o does to prevent inf/nan
    # print hex(~(0xf << 60))
    expectedUllSum &= (~(0xf << 60))
    return (expectedUllSum, expectedFpSum)

#********************************************************************************
class Basic(unittest.TestCase):
    def tearDown(self):
        h2o.check_sandbox_for_errors()

    @classmethod
    def setUpClass(cls):
        global SEED, localhost
        SEED = h2o.setup_random_seed()
        localhost = h2o.decide_if_localhost()
        if (localhost):
            h2o.build_cloud(1, java_heap_GB=28)
        else:
            h2o_hosts.build_cloud_with_hosts(1)

    @classmethod
    def tearDownClass(cls):
        h2o.tear_down_cloud()

    def test_exec2_xorsum2(self):
        h2o.beta_features = True
        SYNDATASETS_DIR = h2o.make_syn_dir()
        tryList = [
            (ROWS, 1, 'r1', 0, 10, None),
        ]

        for trial in range(20):
            ullResultList = []
            NUM_FORMAT_CASES = h2o_util.fp_format()
            for (rowCount, colCount, hex_key, expectedMin, expectedMax, expected) in tryList:
                SEEDPERFILE = random.randint(0, sys.maxint)
                # dynamic range of the data may be useful for estimating error
                maxDelta = expectedMax - expectedMin

                csvFilename = 'syn_real_' + str(rowCount) + 'x' + str(colCount) + '.csv'
                csvPathname = SYNDATASETS_DIR + '/' + csvFilename
                csvPathnameFull = h2i.find_folder_and_filename(None, csvPathname, returnFullPath=True)
                print "Creating random", csvPathname

                sel = random.randint(0, NUM_FORMAT_CASES-1)
                (expectedUllSum, expectedFpSum)  = write_syn_dataset(csvPathname, 
                    rowCount, colCount, expectedMin, expectedMax, SEEDPERFILE, sel)
                expectedUllSumAsDouble = h2o_util.unsignedLongLongToDouble(expectedUllSum)
                expectedFpSumAsLongLong = h2o_util.doubleToUnsignedLongLong(expectedFpSum)

                parseResult = h2i.import_parse(path=csvPathname, schema='local', hex_key=hex_key, 
                    timeoutSecs=3000, retryDelaySecs=2)
                inspect = h2o_cmd.runInspect(key=hex_key)
                print "numRows:", inspect['numRows']
                print "numCols:", inspect['numCols']
                inspect = h2o_cmd.runInspect(key=hex_key, offset=-1)
                print "inspect offset = -1:", h2o.dump_json(inspect)

                
                # looking at the 8 bytes of bits for the h2o doubles
                # xorsum will zero out the sign and exponent
                for execExpr in exprList:
                    start = time.time()
                    (execResult, fpResult) = h2e.exec_expr(h2o.nodes[0], execExpr, 
                        resultKey=None, timeoutSecs=300)
                    print 'exec took', time.time() - start, 'seconds'
                    print "execResult:", h2o.dump_json(execResult)
                    ullResult = h2o_util.doubleToUnsignedLongLong(fpResult)
                    ullResultList.append((ullResult, fpResult))

                    print "%30s" % "ullResult (0.16x):", "0x%0.16x   %s" % (ullResult, fpResult)
                    print "%30s" % "expectedUllSum (0.16x):", "0x%0.16x   %s" % (expectedUllSum, expectedUllSumAsDouble)
                    print "%30s" % "expectedFpSum (0.16x):", "0x%0.16x   %s" % (expectedFpSumAsLongLong, expectedFpSum)

                    # allow diff of the lsb..either way. needed when integers are parsed
                    # if ullResult!=expectedUllSum and abs((ullResult-expectedUllSum)>3):
                    if ullResult!=expectedUllSum:
                        raise Exception("h2o didn't get the same xorsum as python. 0x%0.16x 0x%0.16x" % (ullResult, expectedUllSum))
                        print "h2o didn't get the same xorsum as python. 0x%0.16x 0x%0.16x" % (ullResult, expectedUllSum)

                    # print "%30s" % "hex(bitResult):", hex(ullResult)

                h2o.check_sandbox_for_errors()

                print "first result was from a sum. others are xorsum"
                print "ullResultList:"
                for ullResult, fpResult in ullResultList:
                    print "%30s" % "ullResult (0.16x):", "0x%0.16x   %s" % (ullResult, fpResult)

                print "%30s" % "expectedUllSum (0.16x):", "0x%0.16x   %s" % (expectedUllSum, expectedUllSumAsDouble)
                print "%30s" % "expectedFpSum (0.16x):", "0x%0.16x   %s" % (expectedFpSumAsLongLong, expectedFpSum)




if __name__ == '__main__':
    h2o.unit_main()
